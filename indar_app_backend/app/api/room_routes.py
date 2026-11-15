import uuid
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.db import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.room import Room
from app.schemas.room_schema import RoomOut
from app.services.image_service import validate_image, upload_room_image

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.post("/", response_model=RoomOut, status_code=201)
async def create_room(
    room_name: str = Form(...),
    type: str = Form(...),
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content = await validate_image(image)
    image_url = await upload_room_image(
        content=content,
        filename=image.filename,
        user_id=str(current_user.user_id),
    )
    room = Room(
        user_id=current_user.user_id,
        room_name=room_name,
        type=type,
        image_url=image_url,
    )
    db.add(room)
    await db.flush()
    return room


@router.get("/", response_model=List[RoomOut])
async def list_rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Room)
        .where(Room.user_id == current_user.user_id)
        .order_by(Room.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{room_id}", response_model=RoomOut)
async def get_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Room).where(
            Room.room_id == room_id,
            Room.user_id == current_user.user_id,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    return room


@router.delete("/{room_id}", status_code=204)
async def delete_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Room).where(
            Room.room_id == room_id,
            Room.user_id == current_user.user_id,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    await db.delete(room)