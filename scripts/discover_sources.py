#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from packages.discovery.engine import SourceDiscoveryEngine


async def run_discovery(urls: list[str]) -> None:
    engine = SourceDiscoveryEngine()
    results = []
    for url in urls:
        res = await engine.discover_url(url, probe_network=True)
        results.append(asdict(res))
    print(json.dumps(results, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover ATS / Job-Board platform behind URLs.")
    parser.add_argument("urls", nargs="+", help="One or more URLs to inspect")
    args = parser.parse_args()
    asyncio.run(run_discovery(args.urls))


if __name__ == "__main__":
    main()
