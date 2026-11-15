from typing import List
from urllib.parse import urlencode
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from fastapi import HTTPException
from loguru import logger

from app.models.bundle import Bundle, BundleItem
from app.models.product import Product
from app.models.design import Design
from app.services.product_service import validate_asins


def build_amazon_cart_url(asins: List[str]) -> str:
    """
    Builds a public Amazon India add-to-cart URL.
    Uses /gp/aws/cart/add.html which works WITHOUT an Associates account.
    smart-wagon is Associates-only and will silently fail without an affiliate tag.
    Format: /gp/aws/cart/add.html?ASIN.1=X&Quantity.1=1&ASIN.2=Y&Quantity.2=1
    Supports up to 10 items (Amazon limit).
    """
    if not asins:
        raise HTTPException(status_code=400, detail="No products to build cart with.")

    asins = asins[:10]  # Amazon cart hard limit

    params = {}
    for i, asin in enumerate(asins, start=1):
        params[f"ASIN.{i}"] = asin
        params[f"Quantity.{i}"] = "1"

    query = urlencode(params)
    return f"https://www.amazon.in/gp/aws/cart/add.html?AssociateTag=dummy&{query}"


async def create_bundle(
    design: Design,
    products: List[Product],
    user_id: str,
    db: AsyncSession,
) -> Bundle:
    """
    Creates a Bundle tied to a specific user and design.
    Uses flush only — commit is owned by the calling router so the entire
    request (design + elements + bundle) is one atomic transaction.

    Args:
        design:   The Design this bundle belongs to.
        products: List of Product objects to include.
        user_id:  Supabase auth UUID of the user creating this bundle.
        db:       Async DB session.

    Returns:
        The persisted Bundle instance.
    """
    if not products:
        raise HTTPException(
            status_code=422,
            detail="No products available to create a bundle."
        )

    asins = [p.asin for p in products]
    await validate_asins(asins, db)

    total = round(sum(p.price for p in products), 2)
    cart_url = build_amazon_cart_url(asins)

    bundle = Bundle(
        design_id=design.design_id,
        user_id=user_id,
        total_price=total,
        amazon_cart_url=cart_url,
    )
    db.add(bundle)
    await db.flush()  # get bundle_id before inserting items

    for product in products:
        db.add(BundleItem(
            bundle_id=bundle.bundle_id,
            product_id=product.product_id,
            quantity=1,
        ))

    # ← flush only, NOT commit. The router owns the transaction.
    await db.flush()

    logger.info(
        f"Bundle staged | id={bundle.bundle_id} | "
        f"user={user_id} | items={len(products)} | total=₹{total}"
    )
    return bundle


async def get_user_bundle_history(
    user_id: str,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> List[Bundle]:
    """
    Returns all bundles created by a user, newest first.
    Supports pagination via limit and offset.
    """
    limit = min(limit, 100)  # cap to prevent abuse

    result = await db.execute(
        select(Bundle)
        .where(Bundle.user_id == user_id)
        .order_by(desc(Bundle.created_at))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_bundle_by_id(
    bundle_id: str,
    user_id: str,
    db: AsyncSession,
) -> Bundle:
    """
    Fetches a single bundle by ID, scoped to the requesting user.
    Raises 404 if not found, 403 if it belongs to a different user.
    """
    result = await db.execute(
        select(Bundle).where(Bundle.bundle_id == bundle_id)
    )
    bundle = result.scalar_one_or_none()

    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found.")

    if bundle.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return bundle