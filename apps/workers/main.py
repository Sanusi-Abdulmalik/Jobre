from __future__ import annotations

import asyncio
import logging
import signal

from app.core.database import get_session_factory
from app.services.ingestion_service import IngestionPipelineService
from apps.workers.queues.redis_queue import WorkerTaskQueue
from apps.workers.scheduler.refresh_scheduler import schedule_due_sources
from packages.common.logging import configure_logging

logger = logging.getLogger("jobre.worker")


async def run_worker_loop() -> None:
    configure_logging()
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    queue = WorkerTaskQueue()
    pipeline = IngestionPipelineService()
    session_factory = get_session_factory()
    last_schedule_check = 0.0

    logger.info("Jobre background ingestion worker started.")
    while not stop_event.is_set():
        now_mono = loop.time()
        if now_mono - last_schedule_check >= 60.0:
            last_schedule_check = now_mono
            try:
                if await queue.is_healthy():
                    async with session_factory() as session:
                        count = await schedule_due_sources(session, queue, batch_size=15)
                        if count:
                            logger.info("Scheduled %d due sources for refresh.", count)
            except Exception as exc:
                logger.warning("Scheduler tick error: %s", exc)

        try:
            task = await queue.dequeue_next(timeout_sec=2)
        except Exception:
            await asyncio.sleep(3.0)
            continue

        if not task:
            continue

        source_id = task.get("source_id")
        trigger = task.get("trigger_type", "SCHEDULED")
        attempt = int(task.get("attempt", 1))
        if not source_id:
            continue

        async with session_factory() as session:
            run = await pipeline.execute_source_run(session, source_id, trigger_type=trigger)
            if run.status == "FAILED":
                if attempt < 3:
                    await queue.enqueue_refresh(
                        source_id,
                        priority="LOW",
                        trigger_type="RETRY",
                        attempt=attempt + 1,
                    )
                else:
                    await queue.push_dlq(task, run.error_summary or "Max retries exhausted")

    logger.info("Jobre worker shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(run_worker_loop())
