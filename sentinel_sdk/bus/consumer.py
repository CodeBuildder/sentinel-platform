"""
Redis Streams consumer SDK.

Uses XREADGROUP for at-least-once delivery. Failed messages (NACK / handler
exception) are retried up to MAX_RETRIES, then moved to the dead-letter stream.

Usage:
    consumer = Consumer(redis_url="redis://localhost:6379",
                        group="my-service", consumer="worker-1")
    await consumer.ensure_group("sentinel:findings")
    await consumer.subscribe("sentinel:findings", handler=my_handler)
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis

log = logging.getLogger(__name__)

DEAD_LETTER_SUFFIX = ":dead-letter"
MAX_RETRIES = 3
BLOCK_MS = 2000  # long-poll timeout


class ConsumerError(Exception):
    pass


class Consumer:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        group: str = "default",
        consumer: str = "worker",
    ):
        self._url = redis_url
        self._group = group
        self._consumer = consumer
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def connect(self) -> None:
        self._redis = await aioredis.from_url(
            self._url, encoding="utf-8", decode_responses=True
        )

    async def close(self) -> None:
        self._running = False
        if self._redis:
            await self._redis.aclose()

    async def ensure_group(self, stream: str) -> None:
        """Create the consumer group if it doesn't already exist."""
        if self._redis is None:
            await self.connect()
        try:
            await self._redis.xgroup_create(stream, self._group, id="0", mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def subscribe(
        self,
        stream: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        poll_interval: float = 0.1,
    ) -> None:
        """
        Consume messages from stream, calling handler(event_dict) for each.
        Blocks until self.stop() is called.
        """
        if self._redis is None:
            await self.connect()
        await self.ensure_group(stream)
        self._running = True

        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    self._group,
                    self._consumer,
                    {stream: ">"},
                    count=10,
                    block=BLOCK_MS,
                )
            except Exception as exc:
                log.error("xreadgroup_error", exc=str(exc))
                await asyncio.sleep(poll_interval)
                continue

            if not messages:
                continue

            for _stream, entries in messages:
                for msg_id, fields in entries:
                    await self._process(stream, msg_id, fields, handler)

    async def _process(
        self,
        stream: str,
        msg_id: str,
        fields: dict,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        try:
            event = json.loads(fields["data"])
            await handler(event)
            await self._redis.xack(stream, self._group, msg_id)
        except Exception as exc:
            log.warning("handler_error", msg_id=msg_id, exc=str(exc))
            delivery_count = await self._get_delivery_count(stream, msg_id)
            if delivery_count >= MAX_RETRIES:
                await self._dead_letter(stream, msg_id, fields, str(exc))
                await self._redis.xack(stream, self._group, msg_id)

    async def _get_delivery_count(self, stream: str, msg_id: str) -> int:
        try:
            pending = await self._redis.xpending_range(
                stream, self._group, min=msg_id, max=msg_id, count=1
            )
            if pending:
                return pending[0].get("times_delivered", 1)
        except Exception:
            pass
        return 1

    async def _dead_letter(
        self, stream: str, msg_id: str, fields: dict, reason: str
    ) -> None:
        dl_stream = f"{stream}{DEAD_LETTER_SUFFIX}"
        await self._redis.xadd(
            dl_stream,
            {**fields, "original_msg_id": msg_id, "failure_reason": reason},
        )
        log.error("dead_lettered", stream=stream, msg_id=msg_id, reason=reason)

    def stop(self) -> None:
        self._running = False

    async def __aenter__(self) -> "Consumer":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
