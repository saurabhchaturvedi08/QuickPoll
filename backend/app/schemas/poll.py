from pydantic import BaseModel, Field
from typing import List


class PollOptionCreate(BaseModel):
    id: str
    text: str


class PollCreate(BaseModel):
    question: str
    options: List[PollOptionCreate]


class PollOut(BaseModel):
    id: str = Field(..., alias="_id")
    owner_id: str
    question: str
    options: List[dict]
    likes: int