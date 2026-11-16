import uuid
from typing import List
import random
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database.db import get_db, async_session   # ← import async_session
from app.dependencies import get_current_user
from app.models.user import User
from app.models.room import Room
from app.models.design import Design, DesignElement, Theme
from app.models.bundle import Bundle, BundleItem
from app.models.product import Product
from app.schemas.design_schema import DesignOut, GenerateDesignRequest
from app.schemas.product_schema import BundleDetailOut
import asyncio
import httpx
from app.services.compose_service import compose_room, has_cutout
from app.services.theme_hints import infer_theme, keywords
from app.services.storage_service import get_3d_url, upload_image
from app.services import progress
from app.services.bundle_service import create_bundle

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/designs", tags=["Designs"])


_QUOTA = {"Wall": 2, "Hanging": 2, "Floor": 2}


async def select_catalog_products(theme, prompt, db: AsyncSession):
    # Products to put in the picture. Only products with a real cut-out qualify, so
    # everything shown in the picture can be bought. Words in the prompt (for example
    # "lights" or "gold") move matching products to the front; with no theme the
    # prompt must match a product's name or it is not used.
    query = select(Product).where(Product.is_active == True)
    if theme:
        query = query.where(Product.theme.ilike(theme))
    candidates = [p for p in (await db.execute(query)).scalars().all() if has_cutout(p.asin)]

    words = keywords(prompt)
    scored = []
    for p in candidates:
        haystack = f"{p.name} {p.category} {p.theme}".lower()
        scored.append((sum(1 for w in words if w in haystack), random.random(), p))
    if not theme:
        # No theme: the prompt alone must really match products (two shared words, or
        # every word when it only has one), so "a blue sofa" does not return a random
        # product that merely contains the word "blue".
        needed = min(2, len(words))
        scored = [t for t in scored if needed and t[0] >= needed]
    scored.sort(key=lambda t: (-t[0], t[1]))

    counts, picked = {}, []
    for _, _, p in scored:  # spread over wall / hanging / floor
        if counts.get(p.category, 0) < _QUOTA.get(p.category, 1):
            picked.append(p)
            counts[p.category] = counts.get(p.category, 0) + 1
    return picked


@router.post("/generate", response_model=DesignOut, status_code=201)
@limiter.limit("10/minute")
async def generate_design(
    request: Request,
    body: GenerateDesignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),   # ← used ONLY for pre-flight queries
    x_progress_id: str | None = Header(default=None),
):
    user_id = current_user.user_id

    # -------------------------
    # PHASE 1: Quick DB reads
    # Close this session before the 5-min generation starts
    # -------------------------

    # Step 1: load roomnmvvv
    result = await db.execute(
        select(Room).where(
            Room.room_id == body.room_id,
            Room.user_id == current_user.user_id,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    if not room.image_url:
        raise HTTPException(status_code=422, detail="Room has no uploaded image.")

    # Step 2: resolve the request mode
    #   theme only | prompt only | theme + prompt
    effective_theme = body.theme_name or infer_theme(body.user_prompt)
    theme = None
    if effective_theme:
        result = await db.execute(
            select(Theme).where(Theme.theme_name.ilike(effective_theme))
        )
        theme = result.scalar_one_or_none()
        if not theme and body.theme_name:
            raise HTTPException(
                status_code=404,
                detail=f"Theme '{body.theme_name}' not found. "
                       f"Available: onam, Christmas, Diwali, Halloween, Birthday, Pop-Culture"
            )

    # Step 3a: products to put in the picture (and later the bundle)
    theme_products = await select_catalog_products(effective_theme, body.user_prompt, db)
    if not theme_products:
        raise HTTPException(
            status_code=422,
            detail="No products in our catalog match that yet. Pick a theme, or describe "
                   "decor like lights, wreath, garland, rug or poster.",
        )
    products_data = [
        {
            "product_id": p.product_id,
            "asin": p.asin,
            "name": p.name,
            "category": p.category,
            "asset_3d_name": p.asset_3d_name,
            "theme": p.theme,
        }
        for p in theme_products
    ]

    # Capture everything we need as plain values before closing the session
    room_id = room.room_id
    room_image_url = room.image_url
    theme_id = theme.theme_id if theme else None

    # ✅ Explicitly close the dependency session — don't hold it during generation
    await db.close()

    logger.info(
        f"Mode: theme={body.theme_name!r} prompt={bool(body.user_prompt)} "
        f"(effective theme={effective_theme!r}) with {len(products_data)} products"
    )

    # -------------------------
    # PHASE 2: Slow generation — no DB connection held
    # -------------------------
    # The picture is made by placing the REAL products into the user's own room photo
    # (no AI drawing), so everything shown can be bought.
    try:
        progress.set_stage(user_id, x_progress_id, "preparing")
        async with httpx.AsyncClient(timeout=30) as client:
            room_resp = await client.get(room_image_url)
            room_resp.raise_for_status()

        progress.set_stage(user_id, x_progress_id, "composing")
        items = [
            {"asin": p["asin"], "category": p["category"], "name": p["name"]}
            for p in products_data
        ]
        jpeg, placements = await asyncio.to_thread(compose_room, room_resp.content, items)

        progress.set_stage(user_id, x_progress_id, "saving")
        image_url = await upload_image(
            content=jpeg, filename=f"design_{uuid.uuid4().hex[:6]}.jpg", user_id="ai"
        )
    except Exception as e:
        logger.error(f"Composing the design failed: {e}")
        progress.set_stage(user_id, x_progress_id, "failed")
        raise HTTPException(status_code=500, detail="Could not build the design picture. Please try again.")

    by_asin = {p["asin"]: p for p in products_data}
    z_by_category = {"Wall": 0.3, "Hanging": 0.0, "Floor": 0.6}
    ai_result = {
        "design_image_url": image_url,
        "style": effective_theme or "custom",
        "elements": [
            {
                "name": by_asin[pl["asin"]]["name"],
                "category": pl["category"],
                "pos_x": round((pl["cx"] - 0.5) * 1.6, 3),
                "pos_y": round((1 - pl["cy"]) * 2.5, 3),
                "pos_z": z_by_category.get(pl["category"], 0.3),
                "product_id": by_asin[pl["asin"]]["product_id"],
                "asset_3d_name": by_asin[pl["asin"]]["asset_3d_name"],
                "product_theme": by_asin[pl["asin"]]["theme"],
            }
            for pl in placements
        ],
    }

    progress.set_stage(user_id, x_progress_id, "matching")

    # -------------------------
    # PHASE 3: Fresh DB session for all writes
    # -------------------------
    async with async_session() as fresh_db:
        async with fresh_db.begin():

            # Step 4: save Design
            design = Design(
                room_id=room_id,
                theme_id=theme_id,
                style=ai_result.get("style", effective_theme or "custom"),
                design_image_url=ai_result.get("design_image_url"),
            )
            fresh_db.add(design)
            await fresh_db.flush()

            # Step 5: save DesignElements
            elements = []
            for el in ai_result.get("elements", []):
                element = DesignElement(
                    design_id=design.design_id,
                    name=el.get("name", "unknown"),
                    category=el.get("category"),
                    pos_x=el.get("pos_x"),
                    pos_y=el.get("pos_y"),
                    pos_z=el.get("pos_z"),
                    product_id=el.get("product_id"),
                    asset_3d_name=get_3d_url(
                        el.get("asset_3d_name"), el.get("product_theme")
                    ),
                )
                fresh_db.add(element)
                elements.append(element)

            await fresh_db.flush()

            # Step 6: bundle of exactly the products shown in the design
            product_ids = {el.product_id for el in elements if el.product_id}
            if product_ids:
                try:
                    prod_rows = await fresh_db.execute(
                        select(Product).where(Product.product_id.in_(product_ids))
                    )
                    bundle_products = list(prod_rows.scalars().all())
                    if bundle_products:
                        await create_bundle(
                            design, bundle_products, str(current_user.user_id), fresh_db
                        )
                        logger.info(f"Bundle created with {len(bundle_products)} products")
                except Exception as e:
                    logger.warning(f"Bundle creation skipped: {e}")

        # Step 7: fetch and return fresh design with elements
        result = await fresh_db.execute(
            select(Design)
            .where(Design.design_id == design.design_id)
            .options(selectinload(Design.elements))
        )
        progress.set_stage(user_id, x_progress_id, "done")
        return result.scalar_one()


@router.get("/progress/{progress_id}")
async def generation_progress(
    progress_id: str,
    current_user: User = Depends(get_current_user),
):
    # Current step of a running generation (poll every couple of seconds)
    return progress.get_stage(current_user.user_id, progress_id)


@router.get("/room/{room_id}", response_model=List[DesignOut])
async def list_designs_for_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Design)
        .join(Room)
        .where(
            Design.room_id == room_id,
            Room.user_id == current_user.user_id,
        )
        .options(selectinload(Design.elements))
        .order_by(Design.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{design_id}", response_model=DesignOut)
async def get_design(
    design_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Design)
        .join(Room)
        .where(
            Design.design_id == design_id,
            Room.user_id == current_user.user_id,
        )
        .options(selectinload(Design.elements))
    )
    design = result.scalar_one_or_none()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found.")
    return design


@router.get("/theme/{theme_name}/elements", response_model=List[dict])
async def get_theme_elements(
    theme_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product)
        .where(
            Product.is_active == True,
            Product.theme.ilike(theme_name),
        )
        .order_by(Product.category, Product.price)
    )
    products = result.scalars().all()

    if not products:
        raise HTTPException(
            status_code=404,
            detail=f"No products found for theme '{theme_name}'"
        )

    grouped = {"Wall": [], "Hanging": [], "Floor": []}
    for p in products:
        cat = p.category or "Floor"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "product_id": str(p.product_id),
            "asin": p.asin,
            "name": p.name,
            "price": p.price,
            "category": p.category,
            "image_url": p.image_url,
            "product_url": p.product_url,
            "asset_3d_name": p.asset_3d_name,
        })

    return [
        {"category": category, "count": len(items), "products": items}
        for category, items in grouped.items()
        if items
    ]


@router.get("/{design_id}/bundle", response_model=BundleDetailOut)
async def get_bundle(
    design_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Bundle)
        .join(Design)
        .join(Room)
        .where(
            Bundle.design_id == design_id,
            Room.user_id == current_user.user_id,
        )
        .options(
            selectinload(Bundle.items).selectinload(BundleItem.product)
        )
        .order_by(Bundle.created_at.desc())
        .limit(1)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(
            status_code=404,
            detail="No bundle found for this design."
        )
    return bundle