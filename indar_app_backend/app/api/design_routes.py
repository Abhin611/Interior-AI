import uuid
from typing import List
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
from app.services.ai_service import analyze_room
from app.services.gpu_service import GpuOfflineError, gpu_status, gpu_offline_message
from app.services import progress
from app.services.product_service import match_products_to_elements
from app.services.bundle_service import create_bundle

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/designs", tags=["Designs"])


async def get_products_by_theme(theme: str, db: AsyncSession):
    """Get up to 5 active products for a theme to build AI prompt."""
    result = await db.execute(
        select(Product)
        .where(
            Product.is_active == True,
            Product.theme.ilike(theme),
        )
        .limit(5)
    )
    return result.scalars().all()


@router.post("/generate", response_model=DesignOut, status_code=201)
@limiter.limit("10/minute")
async def generate_design(
    request: Request,
    body: GenerateDesignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),   # ← used ONLY for pre-flight queries
    x_progress_id: str | None = Header(default=None),
):
    # Fail fast (before any work) when the Colab GPU server is not running
    if not (await gpu_status())["online"]:
        raise HTTPException(status_code=503, detail=gpu_offline_message())
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

    # Step 2: resolve theme
    result = await db.execute(
        select(Theme).where(Theme.theme_name.ilike(body.theme_name))
    )
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(
            status_code=404,
            detail=f"Theme '{body.theme_name}' not found. "
                   f"Available: onam, Christmas, Diwali, Halloween, Birthday, Pop-Culture"
        )

    # Step 3a: get theme products for AI prompt
    theme_products = await get_products_by_theme(body.theme_name, db)
    products_data = [
        {"name": p.name, "category": p.category}
        for p in theme_products
    ]

    # Capture everything we need as plain values before closing the session
    room_id = room.room_id
    room_image_url = room.image_url
    theme_id = theme.theme_id

    # ✅ Explicitly close the dependency session — don't hold it during generation
    await db.close()

    logger.info(f"Using {len(products_data)} products for AI prompt: {body.theme_name}")

    # -------------------------
    # PHASE 2: Slow generation — no DB connection held
    # -------------------------
    try:
        ai_result = await analyze_room(
            image_url=room_image_url,
            theme=body.theme_name,
            products=products_data,
            user_prompt=body.user_prompt,
            user_id=user_id,
            progress_id=x_progress_id,
        )
    except GpuOfflineError:
        progress.set_stage(user_id, x_progress_id, "failed")
        raise HTTPException(status_code=503, detail=gpu_offline_message())

    if not ai_result.get("design_image_url"):
        progress.set_stage(user_id, x_progress_id, "failed")
        raise HTTPException(status_code=500, detail="Image generation failed.")

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
                style=ai_result.get("style", body.theme_name),
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
                )
                fresh_db.add(element)
                elements.append(element)

            await fresh_db.flush()

            # Step 6: match products + create bundle
            if elements:
                try:
                    matched_products = await match_products_to_elements(
                        elements=elements,
                        theme=body.theme_name,
                        db=fresh_db,
                    )
                    await fresh_db.flush()

                    if matched_products:
                        await create_bundle(
                            design, matched_products, str(current_user.user_id), fresh_db
                        )
                        logger.info(f"Bundle created with {len(matched_products)} products")

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