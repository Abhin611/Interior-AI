from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user_schema import UserOut, UserUpdateName
from app.services.auth_service import update_user_name

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the current user's profile.
    Also acts as the token verification endpoint —
    Flutter can call this on app start to confirm the token is valid.
    """
    return current_user


@router.patch("/me/name", response_model=UserOut)
async def set_name(
    body: UserUpdateName,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set display name after first Supabase login."""
    return await update_user_name(current_user, body.name, db)