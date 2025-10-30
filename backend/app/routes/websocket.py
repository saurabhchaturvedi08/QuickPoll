from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from app.core.broadcaster import broadcaster, CHANNEL_NAME

router = APIRouter(prefix="/ws", tags=["WebSocket"])

connected_clients = set()

@router.websocket("/polls")
async def polls_ws(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)

    pubsub = await broadcaster.subscribe(CHANNEL_NAME)

    try:
        async def reader():
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    data = json.loads(msg["data"])
                    # Send to all connected clients
                    await broadcast_to_all(data)

        reader_task = asyncio.create_task(reader())

        # Keep connection open
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        reader_task.cancel()

async def broadcast_to_all(data: dict):
    """
    Broadcast message to all connected clients.
    """
    living_clients = set()
    for client in connected_clients:
        try:
            await client.send_json(data)
            living_clients.add(client)
        except Exception:
            pass
    connected_clients.clear()
    connected_clients.update(living_clients)
