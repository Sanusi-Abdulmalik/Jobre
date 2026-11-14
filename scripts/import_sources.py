#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from app.core.database import get_session_factory
from app.services.platform_service import seed_platforms_catalog
from app.services.source_service import register_source


async def import_from_file(path: Path) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await seed_platforms_catalog(session)

        entries: list[dict] = []
        if path.suffix.lower() == ".json":
            entries = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8") as fh:
                entries = list(csv.DictReader(fh))
        else:
            entries = [{"source_url": line.strip()} for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

        created_cnt = 0
        existing_cnt = 0
        for item in entries:
            url = item.get("source_url") or item.get("url")
            if not url:
                continue
            src, created, _ = await register_source(
                session,
                source_url=url,
                source_name=item.get("source_name"),
                company_name=item.get("company_name"),
                platform_key=item.get("platform_key"),
                board_token=item.get("board_token"),
                priority=item.get("priority", "NORMAL"),
                source_config={"max_jobs": int(item["max_jobs"])} if item.get("max_jobs") else {},
                auto_discover=not bool(item.get("platform_key")),
            )
            if created:
                created_cnt += 1
            else:
                existing_cnt += 1
            print(f"[{'NEW' if created else 'EXISTS'}] {src.source_name:45s} -> {src.source_url}")

        print(f"Import complete: {created_cnt} created, {existing_cnt} already registered.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import Jobre sources from JSON, CSV, or URL list.")
    parser.add_argument(
        "file",
        nargs="?",
        default="data/seed/verified_sources.json",
        help="Path to JSON, CSV, or newline-delimited URL file",
    )
    args = parser.parse_args()
    asyncio.run(import_from_file(Path(args.file)))


if __name__ == "__main__":
    main()
