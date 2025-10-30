from datetime import datetime, timedelta
from typing import Dict, Any
from jose import jwt
from app.core.config import settings


def create_access_token(subject: str, extra: Dict[str, Any] = None) -> str:
    to_encode = {"sub": subject}
    if extra:
        to_encode.update(extra)
    expire = datetime.utcnow() + timedelta(seconds=settings.JWT_EXP_SECONDS)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_token(token: str) -> Dict[str, Any]:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    return payload