import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RoomCreate(BaseModel):
    room_name: str
    type: str  # living_room | bedroom | kitchen etc


class RoomOut(BaseModel):
    room_id: uuid.UUID
    room_name: str
    type: str
    image_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}