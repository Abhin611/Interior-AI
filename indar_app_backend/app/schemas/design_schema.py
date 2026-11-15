import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel,field_validator

VALID_THEMES = {"onam", "christmas", "diwali", "halloween", "birthday", "pop-culture"}

class GenerateDesignRequest(BaseModel):
    room_id: uuid.UUID
    theme_name: str
    style: Optional[str] = None
    user_prompt: Optional[str] = None  # ← user customisation

    @field_validator("theme_name")
    @classmethod
    def validate_theme(cls, v):
        if v.lower() not in VALID_THEMES:
            raise ValueError(
                f"Invalid theme. Must be one of: {', '.join(VALID_THEMES)}"
            )
        return v


class ElementOut(BaseModel):
    element_id: uuid.UUID
    name: str
    category: Optional[str] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None

    asset_3d_name: Optional[str] = None
    product_id: Optional[uuid.UUID] = None  # (you'll want this too)

    model_config = {"from_attributes": True}


class DesignOut(BaseModel):
    design_id: uuid.UUID
    room_id: uuid.UUID
    theme_id: Optional[uuid.UUID] = None
    style: Optional[str] = None
    design_image_url: Optional[str] = None
    elements: List[ElementOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}