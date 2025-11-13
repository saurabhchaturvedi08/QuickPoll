from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from typing import Optional, List
from bson import ObjectId
from datetime import datetime
import uuid

from app.db import get_db
from app.routes.auth import get_current_user
from app.core.broadcaster import publish, CHANNEL_NAME
from app.utils.serializers import serialize_poll

from app.schemas.poll import PollCreate as PollCreateSchema, PollOut, PollUpdate

router = APIRouter(prefix="/polls", tags=["Polls"])

# helper: create option id
def new_option_id() -> str:
    return str(uuid.uuid4())

def ensure_objectid(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")

@router.post("/", response_model=PollOut, status_code=status.HTTP_201_CREATED)
async def create_poll(payload: PollCreateSchema, user=Depends(get_current_user)):
    db = get_db()

    owner_id = user["sub"] if user else None
    now = datetime.utcnow()
    options = []
    for opt in payload.options:
        options.append({"id": new_option_id(), "text": opt.text, "count": 0})

    doc = {
        "question": payload.question,
        "options": options,
        "likes": 0,
        "owner_id": owner_id,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.polls.insert_one(doc)
    doc["_id"] = res.inserted_id
    await publish(CHANNEL_NAME, {"action": "poll_created", "poll": serialize_poll(doc)})
    return serialize_poll(doc)

@router.get("/", status_code=status.HTTP_200_OK)
async def list_polls(
    search: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("created_at"),
    order: Optional[int] = Query(-1),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    db = get_db()
    filters = {}
    if search:
        filters["question"] = {"$regex": search, "$options": "i"}
    if owner_id:
        filters["owner_id"] = owner_id

    skip = (page - 1) * limit
    total = await db.polls.count_documents(filters)
    cursor = db.polls.find(filters).sort(sort_by, order).skip(skip).limit(limit)
    polls = [serialize_poll(p) async for p in cursor]
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
        "results": polls,
    }

@router.get("/{poll_id}", response_model=PollOut)
async def get_poll(poll_id: str):
    db = get_db()
    oid = ensure_objectid(poll_id)
    doc = await db.polls.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Poll not found")
    return serialize_poll(doc)

@router.put("/{poll_id}", response_model=PollOut)
async def update_poll(poll_id: str, payload: PollUpdate, user=Depends(get_current_user)):
    """
    Update question and/or replace options for a poll.
    NOTE: Replacing options will reset vote counts — use with care.
    Production: you might instead support adding/removing options with migration of votes.
    """
    db = get_db()
    oid = ensure_objectid(poll_id)
    doc = await db.polls.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Poll not found")
    # optional: check owner
    if doc.get("owner_id") and str(doc.get("owner_id")) != str(user["sub"]):
        raise HTTPException(status_code=403, detail="Only owner can update poll")

    update_doc = {}
    now = datetime.utcnow()
    if payload.question is not None:
        update_doc["question"] = payload.question
    if payload.options is not None:
        # build new options with new ids and zero counts
        new_options = []
        for opt in payload.options:
            new_options.append({"id": new_option_id(), "text": opt.text, "count": 0})
        update_doc["options"] = new_options
        # Invalidate votes collection for this poll (we delete existing votes)
        await db.votes.delete_many({"poll_id": oid})

    if not update_doc:
        raise HTTPException(status_code=400, detail="Nothing to update")
    update_doc["updated_at"] = now
    await db.polls.update_one({"_id": oid}, {"$set": update_doc})
    doc = await db.polls.find_one({"_id": oid})
    await publish(CHANNEL_NAME, {"action": "poll_updated", "poll": serialize_poll(doc)})
    return serialize_poll(doc)

@router.delete("/{poll_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_poll(poll_id: str, user=Depends(get_current_user)):
    db = get_db()
    oid = ensure_objectid(poll_id)
    doc = await db.polls.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Poll not found")
    if doc.get("owner_id") and str(doc.get("owner_id")) != str(user["sub"]):
        raise HTTPException(status_code=403, detail="Only owner can delete poll")

    await db.polls.delete_one({"_id": oid})
    # remove related votes and likes
    await db.votes.delete_many({"poll_id": oid})
    await db.likes.delete_many({"poll_id": oid})
    await publish(CHANNEL_NAME, {"action": "poll_deleted", "poll_id": str(oid)})
    return

# --- Voting endpoints ---

@router.post("/{poll_id}/vote", status_code=status.HTTP_200_OK)
async def cast_vote(poll_id: str, option_id: str = Body(..., embed=True), user=Depends(get_current_user)):
    """
    Cast a vote. Behavior:
     - If user has not voted: insert vote, increment option count.
     - If user previously voted same option: 400 (already voted).
     - If user previously voted different option: switch vote (decrement old option, increment new, update vote doc).
    """
    db = get_db()
    oid = ensure_objectid(poll_id)
    poll = await db.polls.find_one({"_id": oid})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")

    # ensure option exists in poll
    option = next((o for o in poll["options"] if o["id"] == option_id), None)
    if not option:
        raise HTTPException(status_code=404, detail="Option not found in poll")

    user_id = user["sub"]
    existing = await db.votes.find_one({"poll_id": oid, "user_id": user_id})
    now = datetime.utcnow()

    if existing:
        if existing.get("option_id") == option_id:
            raise HTTPException(status_code=400, detail="You already voted this option")
        # switch vote: decrement old option, increment new option, update vote doc
        old_option_id = existing.get("option_id")
        # decrement old
        await db.polls.update_one({"_id": oid, "options.id": old_option_id}, {"$inc": {"options.$.count": -1}})
        # increment new
        await db.polls.update_one({"_id": oid, "options.id": option_id}, {"$inc": {"options.$.count": 1}})
        # update votes collection
        await db.votes.update_one({"_id": existing["_id"]}, {"$set": {"option_id": option_id, "updated_at": now}})
        poll = await db.polls.find_one({"_id": oid})
        await publish(CHANNEL_NAME, {"action": "vote_switched", "poll": serialize_poll(poll), "user_id": str(user_id)})
        return {"message": "Vote switched successfully"}
    else:
        # create vote doc
        await db.votes.insert_one({
            "poll_id": oid,
            "user_id": user_id,
            "option_id": option_id,
            "created_at": now,
            "updated_at": now
        })
        # increment option count
        await db.polls.update_one({"_id": oid, "options.id": option_id}, {"$inc": {"options.$.count": 1}})
        poll = await db.polls.find_one({"_id": oid})
        await publish(CHANNEL_NAME, {"action": "vote_cast", "poll": serialize_poll(poll), "user_id": str(user_id)})
        return {"message": "Vote cast"}

@router.delete("/{poll_id}/vote", status_code=status.HTTP_200_OK)
async def revert_vote(poll_id: str, user=Depends(get_current_user)):
    """
    Revert (remove) an existing vote by the current user on the poll:
     - Find vote, decrement the option's count, delete vote document.
    """
    db = get_db()
    oid = ensure_objectid(poll_id)
    poll = await db.polls.find_one({"_id": oid})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")

    user_id = user["sub"]
    existing = await db.votes.find_one({"poll_id": oid, "user_id": user_id})
    if not existing:
        raise HTTPException(status_code=400, detail="No existing vote to revert")

    option_id = existing.get("option_id")
    # decrement option count
    await db.polls.update_one({"_id": oid, "options.id": option_id}, {"$inc": {"options.$.count": -1}})
    # delete vote record
    await db.votes.delete_one({"_id": existing["_id"]})
    poll = await db.polls.find_one({"_id": oid})
    await publish(CHANNEL_NAME, {"action": "vote_reverted", "poll": serialize_poll(poll), "user_id": str(user_id)})
    return {"message": "Vote reverted"}

# --- Likes endpoints (explicit) ---

@router.post("/{poll_id}/like", status_code=status.HTTP_200_OK)
async def like_poll(poll_id: str, user=Depends(get_current_user)):
    """
    Like a poll. If already liked -> 400 (use /unlike to remove) or you can implement toggle.
    """
    db = get_db()
    oid = ensure_objectid(poll_id)
    poll = await db.polls.find_one({"_id": oid})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    user_id = user["sub"]
    existing = await db.likes.find_one({"poll_id": oid, "user_id": user_id})
    if existing:
        raise HTTPException(status_code=400, detail="Already liked")
    now = datetime.utcnow()
    await db.likes.insert_one({"poll_id": oid, "user_id": user_id, "created_at": now})
    await db.polls.update_one({"_id": oid}, {"$inc": {"likes": 1}})
    poll = await db.polls.find_one({"_id": oid})
    await publish(CHANNEL_NAME, {"action": "liked", "poll": serialize_poll(poll), "user_id": str(user_id)})
    return {"message": "Poll liked"}

@router.delete("/{poll_id}/like", status_code=status.HTTP_200_OK)
async def unlike_poll(poll_id: str, user=Depends(get_current_user)):
    db = get_db()
    oid = ensure_objectid(poll_id)
    poll = await db.polls.find_one({"_id": oid})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    user_id = user["sub"]
    existing = await db.likes.find_one({"poll_id": oid, "user_id": user_id})
    if not existing:
        raise HTTPException(status_code=400, detail="You have not liked this poll")
    await db.likes.delete_one({"_id": existing["_id"]})
    await db.polls.update_one({"_id": oid}, {"$inc": {"likes": -1}})
    poll = await db.polls.find_one({"_id": oid})
    await publish(CHANNEL_NAME, {"action": "unliked", "poll": serialize_poll(poll), "user_id": str(user_id)})
    return {"message": "Poll unliked"}

# --- utility endpoints ---

@router.get("/{poll_id}/my-vote")
async def my_vote(poll_id: str, user=Depends(get_current_user)):
    db = get_db()
    oid = ensure_objectid(poll_id)
    vote = await db.votes.find_one({"poll_id": oid, "user_id": user["sub"]})
    if not vote:
        return {"voted": False}
    return {"voted": True, "option_id": vote.get("option_id")}
