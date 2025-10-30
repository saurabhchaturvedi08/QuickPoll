import aioredis
import asyncio
import json
from app.core.config import settings

CHANNEL_NAME = "polls_channel"

class RedisBroadcaster:
    def __init__(self, url: str):
        self.url = url
        self.redis = None

    async def connect(self):
        if not self.redis:
            self.redis = await aioredis.from_url(self.url, decode_responses=True)

    async def publish(self, channel: str, message: dict):
        if not self.redis:
            await self.connect()
        await self.redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str):
        if not self.redis:
            await self.connect()
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

# Singleton instance
broadcaster = RedisBroadcaster(settings.REDIS_URL)
