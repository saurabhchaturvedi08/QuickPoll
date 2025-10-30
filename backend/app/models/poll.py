from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class PollOption(BaseModel):
    id: str
    text: str
    count: int = 0


class PollInDB(BaseModel):
    id: str = Field(..., alias="_id")
    owner_id: str
    question: str
    options: List[PollOption]
    created_at: datetime
    updated_at: Optional[datetime]
    likes: int = 0