# ensure indexes run at startup
async def create_indexes(db):
    await db.users.create_index("email", unique=True)
    await db.users.create_index("google_id", unique=True, sparse=True)


    await db.polls.create_index([("owner_id", 1)])
    await db.polls.create_index([("created_at", -1)])
    # if options stored as list of dicts with id and text, we might index options.id if needed


    await db.votes.create_index([("poll_id", 1)])
    await db.votes.create_index([("user_id", 1)])
    await db.likes.create_index([("poll_id", 1)])
    await db.likes.create_index([("user_id", 1)])