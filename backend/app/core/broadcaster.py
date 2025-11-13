import asyncio
import json
from typing import Callable, Any

CHANNEL_NAME = "quickpoll:events"

_subscribers = {}

async def publish(channel: str, message: dict):
    # In production publish to Redis/Other
    # Here it's a no-op or in-memory dispatch.
    data = json.dumps(message, default=str)
    # attempt to call coroutine subscribers
    for cb in list(_subscribers.get(channel, [])):
        try:
            if asyncio.iscoroutinefunction(cb):
                await cb(data)
            else:
                cb(data)
        except Exception:
            pass

def subscribe(channel: str, callback: Callable[[Any], Any]):
    _subscribers.setdefault(channel, []).append(callback)

def unsubscribe(channel: str, callback: Callable[[Any], Any]):
    lst = _subscribers.get(channel, [])
    if callback in lst:
        lst.remove(callback)
