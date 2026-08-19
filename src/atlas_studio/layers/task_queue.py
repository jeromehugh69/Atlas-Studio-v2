from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from itertools import count
from uuid import UUID

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
except ImportError:
    Redis = None
    RedisError = OSError

_logger = logging.getLogger("atlas_studio.task_queue")


PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


@dataclass(frozen=True)
class QueuedTask:
    task_id: UUID
    priority: str
    user_authorized: bool


class DurablePriorityQueue:
    """Redis-backed priority queue with a process-local recovery fallback."""

    QUEUE_KEY = "atlas-studio:queue:tasks"
    PAYLOAD_KEY = "atlas-studio:queue:task-payloads"

    def __init__(self):
        self.redis: Redis | None = None
        self.fallback: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.sequence = count()

    def attach(self, redis) -> None:
        self.redis = redis
        if redis is None:
            _logger.info("Task queue: Redis unavailable, using in-memory fallback")

    @staticmethod
    def _score(priority: str) -> float:
        # Priority owns the high digits; enqueue time preserves FIFO ordering.
        return PRIORITY_ORDER[priority] * 10**15 + time.time_ns() // 1_000_000

    async def enqueue(self, task_id: UUID, priority: str, user_authorized: bool) -> None:
        payload = json.dumps({"task_id": str(task_id), "priority": priority, "user_authorized": user_authorized})
        if self.redis:
            try:
                async with self.redis.pipeline(transaction=True) as pipeline:
                    pipeline.hset(self.PAYLOAD_KEY, str(task_id), payload)
                    pipeline.zadd(self.QUEUE_KEY, {str(task_id): self._score(priority)})
                    await pipeline.execute()
                return
            except RedisError:
                pass
        await self.fallback.put((PRIORITY_ORDER[priority], next(self.sequence), payload))

    async def dequeue(self) -> QueuedTask:
        while True:
            if self.redis:
                try:
                    rows = await self.redis.zpopmin(self.QUEUE_KEY, count=1)
                    if rows:
                        task_id = rows[0][0]
                        payload = await self.redis.hget(self.PAYLOAD_KEY, task_id)
                        await self.redis.hdel(self.PAYLOAD_KEY, task_id)
                        if payload:
                            data = json.loads(payload)
                            return QueuedTask(UUID(data["task_id"]), data["priority"], bool(data["user_authorized"]))
                    await asyncio.sleep(0.25)
                    continue
                except (RedisError, ValueError, KeyError, json.JSONDecodeError):
                    pass
            try:
                _, _, payload = await asyncio.wait_for(self.fallback.get(), timeout=0.5)
                data = json.loads(payload)
                return QueuedTask(UUID(data["task_id"]), data["priority"], bool(data["user_authorized"]))
            except asyncio.TimeoutError:
                continue

    async def remove(self, task_id: UUID) -> None:
        if self.redis:
            try:
                async with self.redis.pipeline(transaction=True) as pipeline:
                    pipeline.zrem(self.QUEUE_KEY, str(task_id))
                    pipeline.hdel(self.PAYLOAD_KEY, str(task_id))
                    await pipeline.execute()
            except RedisError:
                pass

    async def depth(self) -> int:
        if self.redis:
            try:
                return int(await self.redis.zcard(self.QUEUE_KEY))
            except RedisError:
                pass
        return self.fallback.qsize()
