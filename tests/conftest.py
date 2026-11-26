from __future__ import annotations

import os
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from packages.common.config import Settings

# Keep tests isolated from the developer database and make paths portable across
# local machines and CI runners. TEST_DATABASE_URL may be supplied by CI; the
# application uses SQLAlchemy's async engine, so normalize sync PostgreSQL DSNs.
def _async_database_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url
    raise ValueError("TEST_DATABASE_URL must be a PostgreSQL URL supported by asyncpg.")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_URL = _async_database_url(
    os.environ.get("TEST_DATABASE_URL") or Settings().test_database_url
)
TEST_RAW_DIR = PROJECT_ROOT / "data" / "raw_snapshots_test"

os.environ["DATABASE_URL"] = TEST_DB_URL
# Settings.raw_storage_path maps to RAW_STORAGE_PATH (not JOBRE_RAW_STORAGE_PATH).
os.environ["RAW_STORAGE_PATH"] = str(TEST_RAW_DIR)
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
