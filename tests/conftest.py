from __future__ import annotations

import os
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# Point test suite strictly at isolated jobre_test database and isolated raw snapshot directory
TEST_DB_URL = "postgresql+asyncpg://jobre@127.0.0.1:5432/jobre_test"
TEST_RAW_DIR = Path("/home/user/jobre/data/raw_snapshots_test")

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["JOBRE_RAW_STORAGE_PATH"] = str(TEST_RAW_DIR)
os.environ["JOBRE_ADMIN_API_KEY"] = "test-admin-secret-key"

from packages.common.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.database import reset_db_engine, get_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.platform_service import seed_platforms_catalog  # noqa: E402


@pytest_asyncio.fixture()
async def db_session():
    get_settings.cache_clear()
    reset_db_engine()
    TEST_RAW_DIR.mkdir(parents=True, exist_ok=True)
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE coverage_evidence, connector_health, duplicate_candidates, "
                "duplicate_groups, job_changes, raw_job_records, ingestion_runs, "
                "source_jobs, jobs, sources, companies, platforms CASCADE;"
            )
        )
        await session.commit()
        await seed_platforms_catalog(session)
        yield session
    reset_db_engine()


@pytest_asyncio.fixture()
async def api_client(db_session):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
