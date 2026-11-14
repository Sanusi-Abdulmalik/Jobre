#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_session_factory
from app.models.entities import Platform, Source
from app.services.ingestion_service import IngestionPipelineService
from app.services.platform_service import build_coverage_report, seed_platforms_catalog
from app.services.source_service import register_source
from packages.common.config import PROJECT_ROOT


def render_coverage_markdown(report: dict) -> str:
    lines = [
        "# Jobre — 78-Platform Coverage & Verification Matrix",
        "",
        f"**Generated At (UTC):** `{report['generated_at']}`  ",
        f"**Total Required Platforms:** `{report['total_required_platforms']}` (58 ATS + 20 Job Boards)  ",
        f"**Status Summary:** `{json.dumps(report['status_summary'])}`",
        "",
        "> **Verification Integrity Rule:** A platform is marked `VERIFIED` **only** when its connector has executed against a real live public source, stored compressed raw snapshots, normalized valid job listings into PostgreSQL, and recorded cryptographic verification evidence.",
        "",
        "| # | Platform | Category | Connector Key | Status | Sources | Jobs Indexed | Active Jobs | Verified Run ID | Example Live Source | Extraction Method |",
        "|---:|---|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for idx, p in enumerate(report["platforms"], start=1):
        ev = p.get("verification_evidence") or {}
        run_short = f"`{ev['verification_run_id'][:8]}`" if ev.get("verification_run_id") else "—"
        src_link = ev.get("example_source_url") or "—"
        method = (p.get("extraction_method") or "").replace("|", "\\|")
        lines.append(
            f"| {idx} | **{p['name']}** | {p['category']} | `{p['connector_key']}` | **{p['implementation_status']}** "
            f"| {p['sources_discovered']} | {p['jobs_indexed']} | {p['active_jobs']} | {run_short} | {src_link} | {method} |"
        )
    lines.append("")
    return "\n".join(lines)


async def verify_all() -> None:
    seed_file = PROJECT_ROOT / "data" / "seed" / "verified_sources.json"
    entries = json.loads(seed_file.read_text(encoding="utf-8"))

    factory = get_session_factory()
    pipeline = IngestionPipelineService()

    async with factory() as session:
        await seed_platforms_catalog(session)

        registered_ids: list[tuple[str, str, int | None]] = []
        for entry in entries:
            src, _created, _ = await register_source(
                session,
                source_url=entry["source_url"],
                source_name=entry.get("source_name"),
                company_name=entry.get("company_name"),
                platform_key=entry.get("platform_key"),
                board_token=entry.get("board_token"),
                priority=entry.get("priority", "NORMAL"),
                source_config={"max_jobs": entry["max_jobs"]} if entry.get("max_jobs") else {},
                auto_discover=False,
            )
            registered_ids.append((src.id, src.source_name, entry.get("max_jobs")))

    print(f"Executing live verification runs across {len(registered_ids)} real sources...")
    for src_id, src_name, max_jobs in registered_ids:
        async with factory() as session:
            run = await pipeline.execute_source_run(
                session,
                src_id,
                trigger_type="VERIFICATION",
                max_jobs_override=max_jobs,
                record_verification=True,
            )
            print(
                f"  [{run.status:9s}] {src_name:44s} | discovered={run.jobs_discovered:3d} "
                f"created={run.jobs_created:3d} dedup={run.jobs_deduplicated:2d} "
                f"time={run.duration_ms}ms"
                + (f" | err={run.error_summary[:80]}" if run.error_summary else "")
            )

    async with factory() as session:
        report = await build_coverage_report(session)

    out_json = PROJECT_ROOT / "data" / "seed" / "latest_coverage_report.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    out_md = PROJECT_ROOT / "docs" / "coverage-matrix.md"
    out_md.write_text(render_coverage_markdown(report), encoding="utf-8")

    print("\nCoverage Summary:", report["status_summary"])
    print("Category Breakdown:", report["category_breakdown"])


if __name__ == "__main__":
    asyncio.run(verify_all())
