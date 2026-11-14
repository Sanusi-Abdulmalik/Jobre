#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from app.core.database import get_session_factory
from packages.search.engine import get_search_coordinator


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        res = await get_search_coordinator().rebuild_index(session)
    print(f"Search projection rebuilt from PostgreSQL: {res}")


if __name__ == "__main__":
    asyncio.run(main())
