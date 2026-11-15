from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.database.db import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.bundle_service import (
    get_user_bundle_history,
    get_bundle_by_id,
)

router = APIRouter(prefix="/bundles", tags=["Bundles"])


# ──────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────

class BundleItemOut(BaseModel):
    product_id: str
    product_name: Optional[str] = None
    asin: Optional[str] = None
    price: Optional[float] = None

    class Config:
        from_attributes = True


class BundleOut(BaseModel):
    bundle_id: str
    design_id: str
    user_id: str
    total_price: float
    amazon_cart_url: str
    created_at: datetime
    items: List[BundleItemOut] = []

    class Config:
        from_attributes = True


class BundleHistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    bundles: List[BundleOut]


# ──────────────────────────────────────────
# Routes
# ──────────────────────────────────────────

@router.get("/history", response_model=BundleHistoryResponse)
async def get_bundle_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # uses your existing JWT dep
):
    """
    Returns the authenticated user's bundle history, newest first.
    Supports pagination via limit and offset query params.
    Requires: Authorization: Bearer <supabase_jwt>
    """
    bundles = await get_user_bundle_history(
        user_id=str(current_user.user_id),
        db=db,
        limit=limit,
        offset=offset,
    )
    return BundleHistoryResponse(
        total=len(bundles),
        limit=limit,
        offset=offset,
        bundles=bundles,
    )


@router.get("/{bundle_id}", response_model=BundleOut)
async def get_bundle_detail(
    bundle_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # uses your existing JWT dep
):
    """
    Returns a single bundle by ID.
    Only accessible by the user who created it.
    Requires: Authorization: Bearer <supabase_jwt>
    """
    bundle = await get_bundle_by_id(
        bundle_id=bundle_id,
        user_id=str(current_user.user_id),
        db=db,
    )
    return bundle