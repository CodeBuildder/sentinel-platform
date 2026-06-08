"""
Redis Streams publisher SDK.

Usage:
    pub = Publisher(redis_url="redis://localhost:6379")
    await pub.publish(event)   # validates schema then XADDs to sentinel:{event_type}
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from sentinel_sdk.schema import validate_event

log = logging.getLogger(__name__)

STREAM_PREFIX = "sentinel"
MAX_STREAM_LEN = 100_000  # approximate cap; trimmed on each publish


class Publisher:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._url = redis_url
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = await aioredis.from_url(
            self._url, encoding="utf-8", decode_responses=True
        )

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def publish(self, event: dict[str, Any]) -> str:
        """Validate then publish an event. Returns the Redis stream message ID."""
        validate_event(event)

        if self._redis is None:
            await self.connect()

        stream = f"{STREAM_PREFIX}:{event['type']}s"  # sentinel:findings, etc.
        msg_id = await self._redis.xadd(
            stream,
            {"data": json.dumps(event)},
            maxlen=MAX_STREAM_LEN,
            approximate=True,
        )
        log.debug("published", stream=stream, event_id=event["event_id"], msg_id=msg_id)
        return msg_id

    async def __aenter__(self) -> "Publisher":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
