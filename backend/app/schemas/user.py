from pydantic import BaseModel, EmailStr
from typing import Optional


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str]
    picture: Optional[str]