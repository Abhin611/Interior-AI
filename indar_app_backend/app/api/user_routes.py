from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user_schema import UserOut, UserUpdateName
from app.services.auth_service import update_user_name

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.patch("/me/name", response_model=UserOut)
async def update_name(
    body: UserUpdateName,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update display name."""
    return await update_user_name(current_user, body.name, db)