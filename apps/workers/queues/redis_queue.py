from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from packages.common.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_KEYS = {
    "HIGH": "jobre:queue:high",
    "NORMAL": "jobre:queue:normal",
    "LOW": "jobre:queue:low",
}
DLQ_KEY = "jobre:queue:dlq"


class WorkerTaskQueue:
    """Priority-tiered Redis task queue with dead-letter queue (DLQ) support."""

    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.redis_url
        self.enabled = settings.redis_enabled

    def _client(self) -> aioredis.Redis:
        return aioredis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=2.0)

    async def is_healthy(self) -> bool:
        if not self.enabled:
            return False
        client = self._client()
        try:
            return bool(await client.ping())
        except Exception:
            return False
        finally:
            await client.aclose()

    async def enqueue_refresh(
        self,
        source_id: str,
        *,
        priority: str = "NORMAL",
        trigger_type: str = "SCHEDULED",
        attempt: int = 1,
    ) -> dict[str, Any]:
        task = {
            "task_id": str(uuid.uuid4()),
            "source_id": source_id,
            "priority": priority.upper() if priority.upper() in QUEUE_KEYS else "NORMAL",
            "trigger_type": trigger_type,
            "attempt": attempt,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }
        q_key = QUEUE_KEYS[task["priority"]]
        client = self._client()
        try:
            await client.rpush(q_key, json.dumps(task))
            return {"queued": True, "queue": q_key, "task": task}
        finally:
            await client.aclose()

    async def dequeue_next(self, timeout_sec: int = 2) -> dict[str, Any] | None:
        client = self._client()
        try:
            res = await client.blpop(
                [QUEUE_KEYS["HIGH"], QUEUE_KEYS["NORMAL"], QUEUE_KEYS["LOW"]],
                timeout=timeout_sec,
            )
            if not res:
                return None
            _q_name, raw_json = res
            return json.loads(raw_json)
        finally:
            await client.aclose()

    async def push_dlq(self, task: dict[str, Any], error_message: str) -> None:
        client = self._client()
        try:
            dead_payload = {
                **task,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": error_message[:1000],
            }
            await client.rpush(DLQ_KEY, json.dumps(dead_payload))
        except Exception as exc:
            logger.warning("Failed to push task to DLQ: %s", exc)
        finally:
            await client.aclose()

    async def queue_depths(self) -> dict[str, int]:
        client = self._client()
        try:
            return {
                "high": int(await client.llen(QUEUE_KEYS["HIGH"])),
                "normal": int(await client.llen(QUEUE_KEYS["NORMAL"])),
                "low": int(await client.llen(QUEUE_KEYS["LOW"])),
                "dlq": int(await client.llen(DLQ_KEY)),
            }
        except Exception:
            return {"high": 0, "normal": 0, "low": 0, "dlq": 0}
        finally:
            await client.aclose()
