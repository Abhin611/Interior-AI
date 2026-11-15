import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.database.db import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.product import Product
from app.models.bundle import Bundle, Transaction
from app.schemas.product_schema import ProductOut
from app.services.storage_service import get_image_url, get_3d_url

router = APIRouter(prefix="/products", tags=["Products"])


def _enrich(product: Product) -> dict:
    """Add image_url + asset_3d_url from Supabase Storage."""
    data = ProductOut.model_validate(product).model_dump()
    theme = product.theme or "default"
    data["image_url"] = get_image_url(product.asset_3d_name, theme)
    data["asset_3d_url"] = get_3d_url(product.asset_3d_name, theme)  # ✅ added theme
    return data


@router.get("/", response_model=List[ProductOut])
async def list_products(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product).where(Product.is_active == True)
    )
    return [_enrich(p) for p in result.scalars().all()]


# ⚠️ theme route MUST be before /{product_id} to avoid conflict
@router.get("/theme/{theme_name}", response_model=List[ProductOut])
async def list_products_by_theme(
    theme_name: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """All products for a theme. Flutter uses this for browse page."""
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
            detail=f"No products found for theme '{theme_name}'."
        )
    return [_enrich(p) for p in products]


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product).where(Product.product_id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return _enrich(product)


@router.post("/bundles/{bundle_id}/purchase", status_code=200)
async def purchase_bundle(
    bundle_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Bundle).where(Bundle.bundle_id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found.")
    if not bundle.amazon_cart_url:
        raise HTTPException(status_code=422, detail="Bundle has no cart URL.")

    transaction = Transaction(
        user_id=current_user.user_id,
        bundle_id=bundle.bundle_id,
        status="redirected",
    )
    db.add(transaction)
    await db.flush()

    logger.info(f"Purchase redirect: user={current_user.user_id} bundle={bundle_id}")

    return {
        "transaction_id": str(transaction.transaction_id),
        "amazon_cart_url": bundle.amazon_cart_url,
    }