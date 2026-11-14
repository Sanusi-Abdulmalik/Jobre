#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from app.core.database import get_session_factory
from app.services.platform_service import seed_platforms_catalog


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await seed_platforms_catalog(session)
    print(f"Seeded platforms catalog: {result}")


if __name__ == "__main__":
    asyncio.run(main())
