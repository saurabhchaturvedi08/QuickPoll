from datetime import datetime
from bson import ObjectId
from .db import get_db
from .models import PollCreate, PollOut
from fastapi import HTTPException

async def create_poll_service(poll: PollCreate, user_id: str):
    db = get_db()
    poll_doc = {
        "title": poll.title,
        "description": poll.description,
        "options": [{"id": str(ObjectId()), "text": option.text, "votes": 0} for option in poll.options],
        "likes": 0,
        "created_at": datetime.utcnow(),
        "status": "active",  # Poll starts as active
        "visibility": poll.visibility,
        "created_by": user_id,
        "expires_at": poll.expires_at,
    }
    result = await db.polls.insert_one(poll_doc)
    poll_doc["_id"] = str(result.inserted_id)
    return poll_doc

async def get_poll_by_id_service(poll_id: str):
    db = get_db()
    poll = await db.polls.find_one({"_id": ObjectId(poll_id)})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    return PollOut(**poll)

async def update_poll_status_service(poll_id: str, status: str):
    db = get_db()
    result = await db.polls.update_one({"_id": ObjectId(poll_id)}, {"$set": {"status": status}})
    return result.modified_count > 0
