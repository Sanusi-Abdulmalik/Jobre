from __future__ import annotations

from typing import Any
import pytest
from sqlalchemy import func, select

from app.models.entities import (
    DuplicateGroup,
    Job,
    JobChange,
    RawJobRecord,
    Source,
    SourceJob,
)
from app.services.ingestion_service import IngestionPipelineService, unmerge_duplicate_group
from app.services.source_service import register_source
from packages.common.http_client import HttpFetchError
from packages.connectors.base import (
    BaseConnector,
    ConnectorHealthResult,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.connectors.registry import ConnectorRegistry
from packages.normalization.engine import NormalizedJobInput, normalize_job_record
from packages.search.engine import SearchCoordinator, SearchQueryParams


class ControllableConnector(BaseConnector):
    connector_key = "greenhouse"
    platform_name = "Greenhouse"
    category = "ATS"

    def __init__(self, http_client=None) -> None:
        super().__init__(http_client=http_client)
        self.mode = "run1"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        return DiscoveryProbeResult(
            detected=True,
            platform_key="greenhouse",
            confidence=0.99,
            board_token="testco",
        )

    async def fetch_jobs(
        self, source: ConnectorSourceConfig, cursor: str | None = None
    ) -> FetchBatchResult:
        if self.mode == "http_500":
            raise HttpFetchError(
                "Simulated upstream 500 error",
                url=source.source_url,
                status_code=500,
            )
        if self.mode == "run1":
            items = [
                {
                    "id": "job-1",
                    "title": "Platform Engineer",
                    "location": "Remote - US",
                    "salary": "$150,000 - $180,000 per year",
                    "description": "<p>Design core ingestion pipelines.</p>",
                    "url": "https://boards.greenhouse.io/testco/jobs/1001",
                },
                {
                    "id": "job-2",
                    "title": "Product Designer",
                    "location": "New York, NY, US",
                    "salary": None,
                    "description": "<p>Design enterprise search workflows.</p>",
                    "url": "https://boards.greenhouse.io/testco/jobs/1002",
                },
            ]
        elif self.mode == "run2_update_and_omit":
            items = [
                {
                    "id": "job-1",
                    "title": "Staff Platform Engineer",
                    "location": "Remote - US",
                    "salary": "$185,000 - $215,000 per year",
                    "description": "<p>Lead core ingestion and search pipelines.</p>",
                    "url": "https://boards.greenhouse.io/testco/jobs/1001",
                }
            ]
        else:
            items = []

        raws = [
            RawJobPayload(
                external_job_id=i["id"],
                raw_data=i,
                source_url=i["url"],
            )
            for i in items
        ]
        return FetchBatchResult(jobs=raws, http_status=200, is_complete=True)

    def normalize(
        self, raw_job: dict[str, Any], source: ConnectorSourceConfig
    ) -> NormalizedJobInput:
        return normalize_job_record(
            external_job_id=raw_job["id"],
            title=raw_job["title"],
            company_name=source.company_name or "TestCo",
            source_job_url=raw_job["url"],
            application_url=raw_job["url"],
            description_html_or_text=raw_job["description"],
            location_raw=raw_job["location"],
            salary_raw=raw_job["salary"],
            employment_type_raw="Full-time",
        )

    async def health_check(
        self, source: ConnectorSourceConfig | None = None
    ) -> ConnectorHealthResult:
        return ConnectorHealthResult(
            healthy=True, status_code=200, latency_ms=10.0, message="OK"
        )


class SyndicatedBoardConnector(BaseConnector):
    connector_key = "niceboard"
    platform_name = "Niceboard"
    category = "JOB_BOARD"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        return DiscoveryProbeResult(
            detected=True, platform_key="niceboard", confidence=0.95
        )

    async def fetch_jobs(
        self, source: ConnectorSourceConfig, cursor: str | None = None
    ) -> FetchBatchResult:
        item = {
            "id": "nb-99",
            "title": "Staff Platform Engineer",
            "company": "TestCo",
            "location": "Remote - US",
            "job_url": "https://example.com/jobs/nb-99-staff-platform-engineer",
            "apply_url": "https://boards.greenhouse.io/testco/jobs/1001",
            "description": "<p>Lead core ingestion and search pipelines.</p>",
        }
        return FetchBatchResult(
            jobs=[
                RawJobPayload(
                    external_job_id="nb-99",
                    raw_data=item,
                    source_url=item["job_url"],
                )
            ],
            http_status=200,
            is_complete=True,
        )

    def normalize(
        self, raw_job: dict[str, Any], source: ConnectorSourceConfig
    ) -> NormalizedJobInput:
        return normalize_job_record(
            external_job_id=raw_job["id"],
            title=raw_job["title"],
            company_name=raw_job["company"],
            source_job_url=raw_job["job_url"],
            application_url=raw_job["apply_url"],
            description_html_or_text=raw_job["description"],
            location_raw=raw_job["location"],
        )

    async def health_check(
        self, source: ConnectorSourceConfig | None = None
    ) -> ConnectorHealthResult:
        return ConnectorHealthResult(
            healthy=True, status_code=200, latency_ms=10.0, message="OK"
        )


class CustomTestRegistry(ConnectorRegistry):
    def __init__(self, ctrl: ControllableConnector, board: SyndicatedBoardConnector):
        super().__init__()
        self._overrides = {"greenhouse": ctrl, "niceboard": board}

    def get_connector(self, connector_key: str) -> BaseConnector:
        if connector_key in self._overrides:
            return self._overrides[connector_key]
        return super().get_connector(connector_key)


@pytest.mark.asyncio
async def test_change_detection_safe_closure_failure_safety_and_dedup_unmerge(db_session):
    # Acceptance Tests 5, 6, 7, 8, 9, 10
    ctrl = ControllableConnector()
    board = SyndicatedBoardConnector()
    search_coord = SearchCoordinator()
    pipeline = IngestionPipelineService(connector_override=ctrl)
    board_pipeline = IngestionPipelineService(connector_override=board)

    src, created, _ = await register_source(
        db_session,
        source_url="https://boards.greenhouse.io/testco",
        company_name="TestCo",
        platform_key="greenhouse",
        board_token="testco",
        auto_discover=False,
    )
    assert created is True

    src_dup, created_dup, _ = await register_source(
        db_session,
        source_url="https://boards.greenhouse.io/testco/?utm_source=duplicate",
        company_name="TestCo",
        platform_key="greenhouse",
        board_token="testco",
        auto_discover=False,
    )
    assert created_dup is False
    assert src_dup.id == src.id

    # Run 1: Discover 2 active jobs + raw snapshots
    run1 = await pipeline.execute_source_run(db_session, src.id, record_verification=True)
    assert run1.status == "SUCCEEDED"
    assert run1.jobs_created == 2

    raw_count = (await db_session.execute(select(func.count(RawJobRecord.id)))).scalar_one()
    assert raw_count == 2

    # Failure Safety (Test 8): Simulate HTTP 500 -> NO jobs closed, source NOT deleted!
    ctrl.mode = "http_500"
    run_fail = await pipeline.execute_source_run(db_session, src.id)
    assert run_fail.status == "FAILED"
    assert run_fail.jobs_closed == 0

    active_after_fail = (
        await db_session.execute(select(func.count(Job.id)).where(Job.status == "ACTIVE"))
    ).scalar_one()
    assert active_after_fail == 2
    src_after_fail = await db_session.get(Source, src.id)
    assert src_after_fail is not None and src_after_fail.consecutive_failures == 1

    # Run 2 (Tests 6 & 7): job-1 updated title/salary; job-2 missing once -> POSSIBLY_CLOSED
    ctrl.mode = "run2_update_and_omit"
    run2 = await pipeline.execute_source_run(db_session, src.id)
    assert run2.status == "SUCCEEDED"
    assert run2.jobs_updated == 1

    jobs_map = {
        j.title: j for j in (await db_session.execute(select(Job))).scalars().all()
    }
    assert "Staff Platform Engineer" in jobs_map
    assert jobs_map["Product Designer"].status == "POSSIBLY_CLOSED"

    changes = (await db_session.execute(select(JobChange))).scalars().all()
    change_types = {c.change_type for c in changes}
    assert "FIELD_MODIFIED" in change_types
    assert "STATUS_TRANSITION" in change_types

    # Run 3 (Test 7): job-2 missing second consecutive healthy run -> CLOSED
    run3 = await pipeline.execute_source_run(db_session, src.id)
    assert run3.status == "SUCCEEDED"
    assert run3.jobs_closed == 1
    designer = (
        await db_session.execute(select(Job).where(Job.title == "Product Designer"))
    ).scalar_one()
    assert designer.status == "CLOSED"
    assert designer.closed_at is not None

    # Cross-source Deduplication + Unmerge (Test 5)
    board_src, _, _ = await register_source(
        db_session,
        source_url="https://example.com",
        company_name="Example Board",
        platform_key="niceboard",
        auto_discover=False,
    )
    run_board = await board_pipeline.execute_source_run(db_session, board_src.id)
    assert run_board.status == "SUCCEEDED"
    assert run_board.jobs_deduplicated == 1

    canonical_job = (
        await db_session.execute(select(Job).where(Job.title == "Staff Platform Engineer"))
    ).scalar_one()
    sjs = (
        await db_session.execute(
            select(SourceJob).where(SourceJob.job_id == canonical_job.id)
        )
    ).scalars().all()
    assert len(sjs) == 2

    dup_group = (await db_session.execute(select(DuplicateGroup))).scalar_one()
    unmerge_res = await unmerge_duplicate_group(db_session, dup_group.id)
    assert unmerge_res["status"] == "UNMERGED"
    assert len(unmerge_res["restored_job_ids"]) == 1

    # Search & Index Recovery (Tests 9 & 10)
    search_page = await search_coord.search(
        db_session,
        SearchQueryParams(q="Platform Engineer", workplace_type="REMOTE", salary_min=160000),
    )
    assert search_page.total >= 1

    rebuild_stats = await search_coord.rebuild_index(db_session)
    assert rebuild_stats["rebuilt_documents"] >= 2
