from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from datetime import datetime
from app.core.db import get_db
from app.core.auth import get_current_user
from app.core.broadcaster import broadcaster
from app.models.polls import PollCreate
from app.utils.serializers import serialize_poll
from fastapi import Query
from typing import Optional
from app.core.broadcaster import CHANNEL_NAME
router = APIRouter(prefix="/polls", tags=["Polls"])


@router.get("/", status_code=status.HTTP_200_OK)
async def list_polls(
    search: Optional[str] = Query(None, description="Search polls by question text"),
    owner_id: Optional[str] = Query(None, description="Filter polls by owner ID"),
    sort_by: Optional[str] = Query("created_at", description="Field to sort by"),
    order: Optional[int] = Query(-1, description="Sort order: 1=ASC, -1=DESC"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    limit: int = Query(10, ge=1, le=100, description="Number of polls per page"),
):
    """
    Get all polls with optional search, filtering, and pagination.

    Examples:
    - /polls?search=AI
    - /polls?owner_id=1234
    - /polls?page=2&limit=5
    - /polls?sort_by=likes&order=-1
    """

    db = get_db()
    filters = {}

    # Apply search filter (case-insensitive)
    if search:
        filters["question"] = {"$regex": search, "$options": "i"}

    # Filter by owner if provided
    if owner_id:
        filters["owner_id"] = owner_id

    # Compute pagination
    skip = (page - 1) * limit

    # Count total docs for pagination info
    total_polls = await db.polls.count_documents(filters)

    # Fetch polls with filters, pagination, and sorting
    cursor = (
        db.polls.find(filters)
        .sort(sort_by, order)
        .skip(skip)
        .limit(limit)
    )

    polls = [serialize_poll(poll) async for poll in cursor]

    return {
        "total": total_polls,
        "page": page,
        "limit": limit,
        "total_pages": (total_polls + limit - 1) // limit,
        "results": polls,
    }



@router.post("/{poll_id}/vote", status_code=status.HTTP_200_OK)
async def vote(poll_id: str, option_id: str, user=Depends(get_current_user)):
    """
    Cast a vote for a given poll option.
    Prevent double voting by the same user.
    """
    db = get_db()

    try:
        poll_obj_id = ObjectId(poll_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid poll ID")

    # Prevent double voting
    existing = await db.votes.find_one({"poll_id": poll_obj_id, "user_id": user["sub"]})
    if existing:
        raise HTTPException(status_code=400, detail="You have already voted on this poll")

    # Increment vote count for the chosen option
    res = await db.polls.update_one(
        {"_id": poll_obj_id, "options.id": option_id},
        {"$inc": {"options.$.count": 1}}
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Poll or option not found")

    # Record the vote
    await db.votes.insert_one({
        "poll_id": poll_obj_id,
        "user_id": user["sub"],
        "option_id": option_id,
        "created_at": datetime.utcnow()
    })

    poll = await db.polls.find_one({"_id": poll_obj_id})
    await broadcaster.publish(CHANNEL_NAME, {"action": "created", "poll": serialize_poll(poll)})

    return {"message": "Vote registered successfully"}


@router.post("/{poll_id}/like", status_code=status.HTTP_200_OK)
async def like_poll(poll_id: str, user=Depends(get_current_user)):
    """
    Toggle like/unlike on a poll.
    """
    db = get_db()

    try:
        poll_obj_id = ObjectId(poll_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid poll ID")

    existing = await db.likes.find_one({"poll_id": poll_obj_id, "user_id": user["sub"]})
    if existing:
        # Unlike the poll
        await db.likes.delete_one({"_id": existing["_id"]})
        await db.polls.update_one({"_id": poll_obj_id}, {"$inc": {"likes": -1}})
        action = "unliked"
    else:
        # Like the poll
        await db.likes.insert_one({
            "poll_id": poll_obj_id,
            "user_id": user["sub"],
            "created_at": datetime.utcnow()
        })
        await db.polls.update_one({"_id": poll_obj_id}, {"$inc": {"likes": 1}})
        action = "liked"

    poll = await db.polls.find_one({"_id": poll_obj_id})
    await broadcaster.publish(CHANNEL_NAME, {"action": "created", "poll": serialize_poll(poll)})

    return {"message": f"Poll successfully {action}"}


@router.get("/", status_code=status.HTTP_200_OK)
async def list_polls():
    """
    Get all polls sorted by creation date.
    """
    db = get_db()
    polls_cursor = db.polls.find().sort("created_at", -1)
    polls = [serialize_poll(p) async for p in polls_cursor]
    return polls
