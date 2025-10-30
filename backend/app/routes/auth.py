from fastapi import APIRouter, HTTPException, Depends
from app.schemas.auth import GoogleTokenIn, Token
from app.core.config import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from app.core.jwt import create_access_token
from app.db.client import get_db
from bson import ObjectId
from datetime import datetime


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=Token)
async def google_login(payload: GoogleTokenIn):
    # Verify Google ID token sent by client
    try:
      idinfo = id_token.verify_oauth2_token(payload.id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except Exception as e:
      raise HTTPException(status_code=401, detail=str(e))


    # idinfo contains: sub (user id), email, picture, name, email_verified
    google_user_id = idinfo.get("sub")
    email = idinfo.get("email")
    name = idinfo.get("name")
    picture = idinfo.get("picture")


    db = get_db()
    existing = await db.users.find_one({"google_id": google_user_id})
    if not existing:
        now = datetime.utcnow()
        doc = {
        "email": email,
        "name": name,
        "picture": picture,
        "google_id": google_user_id,
        "created_at": now,
        }
        res = await db.users.insert_one(doc)
        user_id = str(res.inserted_id)
    else:
        user_id = str(existing.get("_id"))
        # optionally update profile fields
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {"name": name, "picture": picture}})


    token = create_access_token(subject=user_id, extra={"email": email})
    return {"access_token": token}