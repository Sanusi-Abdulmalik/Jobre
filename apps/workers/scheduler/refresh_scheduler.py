from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Platform, Source
from apps.workers.queues.redis_queue import WorkerTaskQueue

logger = logging.getLogger(__name__)


async def schedule_due_sources(
    session: AsyncSession,
    queue: WorkerTaskQueue,
    *,
    batch_size: int = 25,
) -> int:
    """
    Staggered dynamic scheduler: selects due, unlocked sources with implemented connectors
    ordered by priority and staleness, preventing stampedes across 10,000+ sources.
    """
    now = datetime.now(timezone.utc)
    priority_rank = case(
        (Source.priority == "HIGH", 1),
        (Source.priority == "NORMAL", 2),
        else_=3,
    )

    stmt = (
        select(Source)
        .join(Platform, Platform.id == Source.platform_id)
        .where(
            Source.status.in_(("ACTIVE", "DEGRADED")),
            Source.is_test_fixture.is_(False),
            Platform.implementation_status.in_(("IMPLEMENTED", "TESTED", "VERIFIED")),
            or_(Source.next_sync_at.is_(None), Source.next_sync_at <= now),
            or_(Source.sync_lock_until.is_(None), Source.sync_lock_until <= now),
        )
        .order_by(priority_rank.asc(), Source.next_sync_at.asc().nulls_first())
        .limit(batch_size)
    )
    due_sources = (await session.execute(stmt)).scalars().all()
    enqueued = 0
    for src in due_sources:
        await queue.enqueue_refresh(src.id, priority=src.priority, trigger_type="SCHEDULED")
        enqueued += 1
    return enqueued
