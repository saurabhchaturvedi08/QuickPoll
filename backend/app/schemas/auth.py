from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleTokenIn(BaseModel):
    id_token: str