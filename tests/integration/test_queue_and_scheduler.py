from __future__ import annotations

import pytest
import redis.asyncio as aioredis

from apps.workers.queues.redis_queue import WorkerTaskQueue
from apps.workers.scheduler.refresh_scheduler import schedule_due_sources
from app.services.source_service import register_source


@pytest.mark.asyncio
async def test_redis_priority_queue_and_dlq_and_scheduler(db_session):
    test_redis_url = "redis://127.0.0.1:6379/2"
    rc = aioredis.from_url(test_redis_url)
    await rc.flushdb()
    await rc.aclose()

    q = WorkerTaskQueue(redis_url=test_redis_url)
    assert await q.is_healthy() is True

    low_task = await q.enqueue_refresh("src-low", priority="LOW")
    high_task = await q.enqueue_refresh("src-high", priority="HIGH")
    assert low_task["queued"] is True and high_task["queued"] is True

    # HIGH priority dequeues before LOW priority
    popped1 = await q.dequeue_next(timeout_sec=1)
    assert popped1 is not None and popped1["source_id"] == "src-high"

    popped2 = await q.dequeue_next(timeout_sec=1)
    assert popped2 is not None and popped2["source_id"] == "src-low"
    await q.push_dlq(popped2, error_message="Max retries exhausted")

    depths = await q.queue_depths()
    assert depths["dlq"] == 1

    # Staggered scheduler enqueues due implemented sources
    await register_source(
        db_session,
        source_url="https://boards.greenhouse.io/cloudflare",
        company_name="Cloudflare",
        platform_key="greenhouse",
        board_token="cloudflare",
        auto_discover=False,
    )
    sched_res = await schedule_due_sources(db_session, queue=q)
    assert sched_res >= 1
