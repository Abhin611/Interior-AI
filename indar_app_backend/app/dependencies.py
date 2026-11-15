import uuid
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import oauth2_scheme
from app.utils.jwt_handler import decode_supabase_token
from app.database.db import get_db
from app.models.user import User


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Extract token string from credentials object
        token = credentials.credentials
        payload = await decode_supabase_token(token)
        user_id: str = payload.get("sub")
        email: str = payload.get("email")

        if not user_id or not email:
            raise credentials_exception

    except (JWTError, ValueError):
        raise credentials_exception
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach the auth server to verify the token.",
        )

    result = await db.execute(
        select(User).where(User.user_id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(user_id=uuid.UUID(user_id), email=email)
        db.add(user)
        await db.flush()

    return user