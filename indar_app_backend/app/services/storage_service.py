import uuid
from loguru import logger
from fastapi import HTTPException
from supabase import create_client, Client
from app.core.settings import settings


def get_supabase_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def upload_image(content: bytes, filename: str, user_id: str) -> str:
    """Upload AI generated image to Supabase Storage. Returns public URL."""
    try:
        path = f"ai-generated/{user_id}_{filename}"

        supabase = get_supabase_client()
        supabase.storage.from_("assets").upload(
            path=path,
            file=content,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )

        url = f"{settings.SUPABASE_URL}/storage/v1/object/public/assets/{path}"
        logger.info(f"Uploaded to Supabase: {url}")
        return url

    except Exception as e:
        logger.error(f"Supabase Storage upload failed: {e}")
        raise HTTPException(
            status_code=502, detail="Image upload failed. Please try again."
        )


async def upload_room_photo(content: bytes, user_id: str, filename: str) -> str:
    """Upload user room photo to user_image folder. Returns public URL."""
    try:
        path = f"user_image/{user_id}/{filename}"  # ← fixed

        supabase = get_supabase_client()
        supabase.storage.from_("assets").upload(
            path=path,
            file=content,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )

        url = f"{settings.SUPABASE_URL}/storage/v1/object/public/assets/{path}"
        logger.info(f"Room photo uploaded: {url}")
        return url

    except Exception as e:
        logger.error(f"Room photo upload failed: {e}")
        raise HTTPException(
            status_code=502, detail="Room photo upload failed."
        )


def get_image_url(asset_name: str, theme: str) -> str:
    """Get public URL for a product image."""
    if not asset_name or not theme:
        return None
    # Strip full URL if accidentally stored
    name = asset_name.strip()
    if name.startswith('http'):
        name = name.split('/')[-1]
    # Remove extension if present
    if name.endswith('.jpg'):
        name = name[:-4]
    if name.endswith('.png'):
        name = name[:-4]
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/assets/dataset/{theme}/Image/{name}.jpg"


def get_3d_url(asset_name: str, theme: str) -> str:
    """Get public URL for a .glb 3D model."""
    if not asset_name or not theme:
        return None
    # Strip full URL if accidentally stored
    name = asset_name.strip()
    if name.startswith('http'):
        name = name.split('/')[-1]
    # Remove .glb if already present to avoid double extension
    if name.endswith('.glb'):
        name = name[:-4]
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/assets/dataset/{theme}/3d/{name}.glb"