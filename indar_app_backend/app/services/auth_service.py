# Supabase handles register / login / logout / refresh
# This service only handles syncing the Supabase user into our DB
# and updating profile info (e.g. name) after first login

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from loguru import logger

from app.models.user import User


async def update_user_name(user: User, name: str, db: AsyncSession) -> User:
    """Let user set their display name after first login."""
    if not name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be blank.")
    user.name = name.strip()
    await db.flush()
    logger.info(f"User name updated: {user.email} → {name}")
    return user