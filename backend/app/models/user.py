from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class UserInDB(BaseModel):
    id: str = Field(..., alias="_id")
    email: EmailStr
    name: Optional[str]
    picture: Optional[str]
    google_id: Optional[str]
    created_at: datetime