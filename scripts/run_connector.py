#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.entities import Platform, Source
from app.services.ingestion_service import IngestionPipelineService


async def run_target(target: str, max_jobs: int | None) -> None:
    factory = get_session_factory()
    pipeline = IngestionPipelineService()
    async with factory() as session:
        src = await session.get(Source, target)
        if src is None:
            src = (
                await session.execute(
                    select(Source)
                    .join(Platform, Platform.id == Source.platform_id)
                    .where(Platform.connector_key == target)
                    .limit(1)
                )
            ).scalar_one_or_none()
        if src is None:
            raise SystemExit(f"No source found matching source_id or connector_key '{target}'.")

        run = await pipeline.execute_source_run(
            session,
            src.id,
            trigger_type="MANUAL",
            max_jobs_override=max_jobs,
            record_verification=True,
        )
        print(
            f"Run {run.id} [{run.status}] | discovered={run.jobs_discovered} "
            f"created={run.jobs_created} updated={run.jobs_updated} "
            f"dedup={run.jobs_deduplicated} closed={run.jobs_closed} duration={run.duration_ms}ms"
        )
        if run.error_summary:
            print(f"Error: {run.error_summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a Jobre connector against a registered source.")
    parser.add_argument("target", help="Source UUID or connector_key (e.g. greenhouse)")
    parser.add_argument("--max-jobs", type=int, default=None, help="Optional cap on jobs fetched")
    args = parser.parse_args()
    asyncio.run(run_target(args.target, args.max_jobs))


if __name__ == "__main__":
    main()
