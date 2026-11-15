import io
import filetype
from PIL import Image
from fastapi import HTTPException, UploadFile
from loguru import logger
from app.services.storage_service import upload_room_photo  # ← fixed import

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_MB = 10
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024


async def validate_image(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Max size is {MAX_SIZE_MB}MB."
        )

    kind = filetype.guess(content)
    if kind is None or kind.mime not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Invalid format. Only JPEG, PNG, WEBP allowed."
        )

    return content


def _resize(content: bytes) -> bytes:
    try:
        Image.MAX_IMAGE_PIXELS = 20_000_000
        img = Image.open(io.BytesIO(content))

        if img.width > 1920 or img.height > 1920:
            img.thumbnail((1920, 1920), Image.LANCZOS)

        output = io.BytesIO()
        fmt = img.format or "JPEG"
        img.save(output, format=fmt, optimize=True, quality=85)
        return output.getvalue()

    except Exception as e:
        logger.error(f"Image resize failed: {e}")
        raise HTTPException(
            status_code=400,
            detail="Could not process image. File may be corrupted."
        )


async def upload_room_image(
    content: bytes,
    filename: str,
    user_id: str,
) -> str:
    """Resize then upload to Supabase Storage under user_image folder."""
    content = _resize(content)
    return await upload_room_photo(content, user_id, filename)  # ← fixed call