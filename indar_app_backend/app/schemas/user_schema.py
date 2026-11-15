import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

class UserUpdateName(BaseModel):
    name: str