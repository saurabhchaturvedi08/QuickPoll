from fastapi import FastAPI
from app.routes import polls, websocket
from app.core.broadcaster import broadcaster

app = FastAPI(title="QuickPoll API", version="1.0")

# Routers
app.include_router(polls.router)
app.include_router(websocket.router)

@app.on_event("startup")
async def startup_event():
    await broadcaster.connect()
