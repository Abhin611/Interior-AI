from typing import List, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from loguru import logger

from app.models.product import Product
from app.models.design import DesignElement
from app.services.storage_service import get_3d_url, get_image_url  # ← import


async def match_products_to_elements(
    elements: List[DesignElement],
    theme: Optional[str],
    db: AsyncSession,
) -> List[Product]:
    used_product_ids: Set = set()

    for element in elements:
        product = await _find_product(
            category=element.category,
            theme=theme,
            db=db,
            exclude_ids=used_product_ids,
        )

        if product:
            element.product_id = product.product_id
            element.asset_3d_name = get_3d_url(product.asset_3d_name, product.theme)  # ← full URL now
            used_product_ids.add(product.product_id)
            logger.info(
                f"Matched element '{element.name}' → "
                f"'{product.name[:40]}' "
                f"(theme={product.theme}, category={product.category}, "
                f"asset={element.asset_3d_name})"
            )
        else:
            logger.warning(
                f"No product found for element '{element.name}' "
                f"theme={theme}"
            )

    seen: set = set()
    unique: List[Product] = []
    for element in elements:
        if element.product_id and element.product_id not in seen:
            seen.add(element.product_id)
            result = await db.execute(
                select(Product).where(Product.product_id == element.product_id)
            )
            product = result.scalar_one_or_none()
            if product:
                unique.append(product)

    return unique


async def _find_product(
    category: Optional[str],
    theme: Optional[str],
    db: AsyncSession,
    exclude_ids: Optional[Set] = None,
) -> Optional[Product]:
    exclude_ids = exclude_ids or set()

    # Priority 1: theme + category
    if theme and category:
        q = (
            select(Product)
            .where(
                Product.is_active == True,
                Product.theme.ilike(theme),
                Product.category.ilike(category),
            )
            .order_by(Product.price)
        )
        if exclude_ids:
            q = q.where(Product.product_id.notin_(exclude_ids))
        result = await db.execute(q.limit(1))
        product = result.scalar_one_or_none()
        if product:
            return product

    # Priority 2: theme only
    if theme:
        q = (
            select(Product)
            .where(
                Product.is_active == True,
                Product.theme.ilike(theme),
            )
            .order_by(Product.price)
        )
        if exclude_ids:
            q = q.where(Product.product_id.notin_(exclude_ids))
        result = await db.execute(q.limit(1))
        product = result.scalar_one_or_none()
        if product:
            logger.info(f"Used theme-only fallback for category='{category}'")
            return product

    # Priority 3: anything active
    q = select(Product).where(Product.is_active == True)
    if exclude_ids:
        q = q.where(Product.product_id.notin_(exclude_ids))
    result = await db.execute(q.limit(1))
    product = result.scalar_one_or_none()
    if product:
        logger.warning(f"Used last-resort fallback product for theme='{theme}'")
    return product


async def validate_asins(asins: List[str], db: AsyncSession) -> List[Product]:
    result = await db.execute(
        select(Product).where(Product.asin.in_(asins))
    )
    products = result.scalars().all()

    found = {p.asin for p in products}
    missing = set(asins) - found
    inactive = {p.asin for p in products if not p.is_active}

    if missing or inactive:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Some products are unavailable.",
                "missing_asins": list(missing),
                "inactive_asins": list(inactive),
            }
        )
    return list(products)


async def get_products_by_theme(
    theme: str,
    db: AsyncSession,
) -> List[Product]:
    result = await db.execute(
        select(Product)
        .where(
            Product.is_active == True,
            Product.theme.ilike(theme),
        )
        .order_by(Product.category, Product.price)
    )
    return result.scalars().all()