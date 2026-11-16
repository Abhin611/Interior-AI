import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator, model_validator

VALID_THEMES = {"onam", "christmas", "diwali", "halloween", "birthday", "pop-culture"}

class GenerateDesignRequest(BaseModel):
    room_id: uuid.UUID
    # Three ways to ask for a design:
    #   theme only, prompt only, or theme + prompt (the prompt adjusts the theme).
    theme_name: Optional[str] = None
    style: Optional[str] = None
    user_prompt: Optional[str] = None

    @field_validator("theme_name")
    @classmethod
    def validate_theme(cls, v):
        if v is None or not v.strip():
            return None
        if v.lower() not in VALID_THEMES:
            raise ValueError(
                f"Invalid theme. Must be one of: {', '.join(sorted(VALID_THEMES))}"
            )
        return v

    @field_validator("user_prompt")
    @classmethod
    def clean_prompt(cls, v):
        v = (v or "").strip()
        return v[:500] or None

    @model_validator(mode="after")
    def need_theme_or_prompt(self):
        if not self.theme_name and not self.user_prompt:
            raise ValueError("Pick a theme, write a prompt, or both.")
        return self


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