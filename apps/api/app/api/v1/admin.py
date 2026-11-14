from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.dependencies.auth import require_admin_auth
from app.models.entities import (
    DuplicateCandidate,
    DuplicateGroup,
    IngestionRun,
    Job,
    JobChange,
    Platform,
    RawJobRecord,
    Source,
    SourceJob,
)
from app.schemas.api_schemas import (
    BulkImportSourcesRequest,
    CreateSourceRequest,
    DiscoverSourceRequest,
    RefreshSourceRequest,
    TestConnectorRequest,
)
from app.services.ingestion_service import IngestionPipelineService, unmerge_duplicate_group
from app.services.platform_service import build_coverage_report
from app.services.source_service import register_source
from apps.workers.queues.redis_queue import WorkerTaskQueue
from apps.workers.scheduler.refresh_scheduler import schedule_due_sources
from packages.common.security import SSRFSafetyError
from packages.connectors.base import ConnectorSourceConfig
from packages.connectors.registry import get_connector_registry
from packages.discovery.engine import SourceDiscoveryEngine
from packages.search.engine import get_search_coordinator

router = APIRouter(
    prefix="/admin",
    tags=["Administrative API"],
    dependencies=[Depends(require_admin_auth)],
)


@router.get("/auth/verify")
async def verify_admin_credentials() -> dict[str, Any]:
    return {"authenticated": True, "role": "admin"}


@router.post("/sources/discover")
async def discover_candidate_source(
    payload: DiscoverSourceRequest,
) -> dict[str, Any]:
    engine = SourceDiscoveryEngine()
    try:
        result = await engine.discover_url(payload.url, probe_network=True)
    except SSRFSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "input_url": result.input_url,
        "canonical_source_url": result.canonical_source_url,
        "canonical_domain": result.canonical_domain,
        "detected": result.detected,
        "platform_key": result.platform_key,
        "platform_name": result.platform_name,
        "platform_category": result.platform_category,
        "connector_implemented": result.connector_implemented,
        "board_token": result.board_token,
        "company_name": result.company_name,
        "source_type": result.source_type,
        "discovery_method": result.discovery_method,
        "confidence": result.confidence,
        "evidence": result.evidence,
    }


@router.post("/sources")
async def create_source_endpoint(
    payload: CreateSourceRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        src, created, disc = await register_source(
            session,
            source_url=payload.source_url,
            source_name=payload.source_name,
            company_name=payload.company_name,
            platform_key=payload.platform_key,
            board_token=payload.board_token,
            priority=payload.priority,
            source_config={"max_jobs": payload.max_jobs} if payload.max_jobs else {},
        )
    except SSRFSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_summary = None
    if payload.run_immediately and src.platform and get_connector_registry().has_connector(src.platform.connector_key):
        pipeline = IngestionPipelineService()
        run = await pipeline.execute_source_run(
            session,
            src.id,
            trigger_type="MANUAL",
            max_jobs_override=payload.max_jobs,
            record_verification=True,
        )
        run_summary = {
            "id": run.id,
            "status": run.status,
            "jobs_discovered": run.jobs_discovered,
            "jobs_created": run.jobs_created,
            "jobs_updated": run.jobs_updated,
            "jobs_deduplicated": run.jobs_deduplicated,
            "error_summary": run.error_summary,
        }

    return {
        "created": created,
        "source": {
            "id": src.id,
            "source_name": src.source_name,
            "source_url": src.source_url,
            "board_token": src.board_token,
            "status": src.status,
            "company_name": src.company.name if src.company else None,
            "platform_name": src.platform.name if src.platform else None,
            "platform_key": src.platform.connector_key if src.platform else None,
            "discovery_method": src.discovery_method,
            "discovery_confidence": src.discovery_confidence,
        },
        "discovery": (
            {
                "detected": disc.detected,
                "platform_key": disc.platform_key,
                "confidence": disc.confidence,
                "evidence": disc.evidence,
            }
            if disc
            else None
        ),
        "initial_run": run_summary,
    }


@router.post("/sources/bulk")
async def bulk_import_sources(
    payload: BulkImportSourcesRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    created_count = 0
    existing_count = 0
    failed_count = 0

    for raw_url in payload.urls:
        clean = raw_url.strip()
        if not clean:
            continue
        try:
            src, created, _disc = await register_source(
                session,
                source_url=clean,
                priority=payload.priority,
            )
            if created:
                created_count += 1
            else:
                existing_count += 1
            results.append(
                {
                    "url": clean,
                    "status": "created" if created else "existing",
                    "source_id": src.id,
                    "platform_key": src.platform.connector_key if src.platform else None,
                }
            )
        except Exception as exc:
            failed_count += 1
            results.append({"url": clean, "status": "failed", "error": str(exc)})

    return {
        "submitted": len(payload.urls),
        "created": created_count,
        "existing": existing_count,
        "failed": failed_count,
        "results": results,
    }


@router.post("/sources/{source_id}/refresh")
async def trigger_source_refresh(
    source_id: str,
    payload: RefreshSourceRequest = RefreshSourceRequest(),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    src = (
        await session.execute(
            select(Source).where(Source.id == source_id).options(selectinload(Source.platform))
        )
    ).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")

    if not src.platform or not get_connector_registry().has_connector(src.platform.connector_key):
        raise HTTPException(
            status_code=422,
            detail=f"Source platform '{src.platform.name if src.platform else 'Unknown'}' does not have an active connector.",
        )

    if not payload.execute_inline:
        queue = WorkerTaskQueue()
        if await queue.is_healthy():
            queued = await queue.enqueue_refresh(source_id, priority=src.priority, trigger_type="MANUAL")
            return {"mode": "queued", **queued}

    pipeline = IngestionPipelineService()
    run = await pipeline.execute_source_run(
        session,
        source_id,
        trigger_type="MANUAL",
        max_jobs_override=payload.max_jobs,
        record_verification=payload.record_verification,
    )
    return {
        "mode": "inline",
        "run": {
            "id": run.id,
            "source_id": run.source_id,
            "connector_id": run.connector_id,
            "status": run.status,
            "http_status": run.http_status,
            "is_complete_snapshot": run.is_complete_snapshot,
            "duration_ms": run.duration_ms,
            "jobs_discovered": run.jobs_discovered,
            "jobs_processed": run.jobs_processed,
            "jobs_created": run.jobs_created,
            "jobs_updated": run.jobs_updated,
            "jobs_deduplicated": run.jobs_deduplicated,
            "jobs_missing": run.jobs_missing,
            "jobs_closed": run.jobs_closed,
            "errors_count": run.errors_count,
            "error_summary": run.error_summary,
        },
    }


@router.get("/runs")
async def list_ingestion_runs(
    status: str | None = Query(default=None),
    connector_id: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = (
        select(IngestionRun)
        .join(Source, Source.id == IngestionRun.source_id)
        .where(Source.is_test_fixture.is_(False))
        .options(selectinload(IngestionRun.source).selectinload(Source.platform))
    )
    if status:
        stmt = stmt.where(IngestionRun.status == status.upper())
    if connector_id:
        stmt = stmt.where(IngestionRun.connector_id == connector_id.lower())
    if source_id:
        stmt = stmt.where(IngestionRun.source_id == source_id)

    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
    rows = (
        await session.execute(
            stmt.order_by(desc(IngestionRun.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "source_id": r.source_id,
                "source_name": r.source.source_name if r.source else None,
                "source_url": r.source.source_url if r.source else None,
                "platform_name": r.source.platform.name if (r.source and r.source.platform) else None,
                "connector_id": r.connector_id,
                "trigger_type": r.trigger_type,
                "status": r.status,
                "is_complete_snapshot": r.is_complete_snapshot,
                "http_status": r.http_status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_ms": r.duration_ms,
                "jobs_discovered": r.jobs_discovered,
                "jobs_processed": r.jobs_processed,
                "jobs_created": r.jobs_created,
                "jobs_updated": r.jobs_updated,
                "jobs_deduplicated": r.jobs_deduplicated,
                "jobs_missing": r.jobs_missing,
                "jobs_closed": r.jobs_closed,
                "errors_count": r.errors_count,
                "error_summary": r.error_summary,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total > 0 else 0,
    }


@router.get("/runs/{run_id}")
async def get_ingestion_run_detail(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    run = (
        await session.execute(
            select(IngestionRun)
            .where(IngestionRun.id == run_id)
            .options(selectinload(IngestionRun.source).selectinload(Source.platform))
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Ingestion run '{run_id}' not found.")

    raw_samples = (
        await session.execute(
            select(RawJobRecord)
            .where(RawJobRecord.ingestion_run_id == run_id)
            .order_by(RawJobRecord.fetched_at.asc())
            .limit(10)
        )
    ).scalars().all()

    return {
        "id": run.id,
        "source_id": run.source_id,
        "source_name": run.source.source_name if run.source else None,
        "source_url": run.source.source_url if run.source else None,
        "connector_id": run.connector_id,
        "trigger_type": run.trigger_type,
        "status": run.status,
        "is_complete_snapshot": run.is_complete_snapshot,
        "http_status": run.http_status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": run.duration_ms,
        "jobs_discovered": run.jobs_discovered,
        "jobs_processed": run.jobs_processed,
        "jobs_created": run.jobs_created,
        "jobs_updated": run.jobs_updated,
        "jobs_deduplicated": run.jobs_deduplicated,
        "jobs_missing": run.jobs_missing,
        "jobs_closed": run.jobs_closed,
        "errors_count": run.errors_count,
        "error_summary": run.error_summary,
        "run_metadata": run.run_metadata,
        "raw_record_samples": [
            {
                "id": rr.id,
                "external_job_id": rr.external_job_id,
                "content_hash": rr.content_hash,
                "storage_location": rr.storage_location,
                "extraction_version": rr.extraction_version,
                "processing_status": rr.processing_status,
                "fetched_at": rr.fetched_at.isoformat() if rr.fetched_at else None,
            }
            for rr in raw_samples
        ],
    }


@router.get("/connectors")
async def list_admin_connectors(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    report = await build_coverage_report(session)
    registry = get_connector_registry()
    items = []
    for p in report["platforms"]:
        key = p["connector_key"]
        items.append(
            {
                **p,
                "connector_registered_in_code": registry.has_connector(key),
            }
        )
    return {"total": len(items), "items": items}


@router.get("/coverage")
async def get_admin_coverage(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await build_coverage_report(session)


@router.post("/connectors/{connector_id}/test")
async def test_connector_endpoint(
    connector_id: str,
    payload: TestConnectorRequest = TestConnectorRequest(),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    registry = get_connector_registry()
    if not registry.has_connector(connector_id):
        raise HTTPException(
            status_code=422,
            detail=f"Connector '{connector_id}' is cataloged as NOT_IMPLEMENTED and cannot execute live tests yet.",
        )

    target_url = payload.source_url
    board_token = payload.board_token
    company_name = payload.company_name

    if not target_url:
        # Look up an existing registered source for this platform
        existing_src = (
            await session.execute(
                select(Source)
                .join(Platform, Platform.id == Source.platform_id)
                .where(Platform.connector_key == connector_id, Source.is_test_fixture.is_(False))
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing_src is None:
            raise HTTPException(
                status_code=400,
                detail=f"Provide a 'source_url' to test '{connector_id}' (no registered source found in DB).",
            )
        target_url = existing_src.source_url
        board_token = existing_src.board_token
        company_name = existing_src.source_name

    connector = registry.get_connector(connector_id)
    cfg = ConnectorSourceConfig(
        source_id="ephemeral-test",
        source_name=company_name,
        source_url=target_url,
        company_name=company_name,
        board_token=board_token,
        extra_config={"max_jobs": 5},
    )
    health = await connector.health_check(cfg)
    sample_normalized = None
    if health.healthy:
        batch = await connector.fetch_jobs(cfg)
        if batch.jobs:
            norm = connector.normalize(batch.jobs[0].raw_data, cfg)
            sample_normalized = {
                "external_job_id": norm.external_job_id,
                "title": norm.title,
                "company_name": norm.company_name,
                "location_raw": norm.location_raw,
                "employment_type": norm.employment_type,
                "workplace_type": norm.workplace_type,
                "application_url": norm.application_url,
            }

    return {
        "connector_id": connector_id,
        "tested_url": target_url,
        "healthy": health.healthy,
        "status_code": health.status_code,
        "latency_ms": health.latency_ms,
        "message": health.message,
        "sample_normalized_job": sample_normalized,
    }


@router.get("/duplicates")
async def list_duplicate_groups(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = (
        select(DuplicateGroup)
        .options(selectinload(DuplicateGroup.candidates))
        .order_by(desc(DuplicateGroup.created_at))
        .limit(100)
    )
    if status:
        stmt = stmt.where(DuplicateGroup.resolution_status == status.upper())

    groups = (await session.execute(stmt)).scalars().all()
    items: list[dict[str, Any]] = []
    for g in groups:
        canon = (
            await session.execute(
                select(Job)
                .where(Job.id == g.canonical_job_id)
                .options(
                    selectinload(Job.company),
                    selectinload(Job.source_jobs).selectinload(SourceJob.source).selectinload(Source.platform),
                )
            )
        ).scalar_one_or_none()
        if canon is None or canon.is_synthetic:
            continue

        cand_list = []
        for c in g.candidates:
            cand_job = await session.get(Job, c.candidate_job_id) if c.candidate_job_id else None
            cand_sj = (
                await session.execute(
                    select(SourceJob)
                    .where(SourceJob.id == c.source_job_id)
                    .options(selectinload(SourceJob.source).selectinload(Source.platform))
                )
            ).scalar_one_or_none() if c.source_job_id else None

            cand_list.append(
                {
                    "id": c.id,
                    "candidate_job_id": c.candidate_job_id,
                    "candidate_title": (
                        cand_sj.title_at_source
                        if cand_sj and cand_sj.title_at_source
                        else (cand_job.title if cand_job else None)
                    ),
                    "source_name": cand_sj.source.source_name if (cand_sj and cand_sj.source) else None,
                    "platform_name": (
                        cand_sj.source.platform.name
                        if (cand_sj and cand_sj.source and cand_sj.source.platform)
                        else None
                    ),
                    "source_job_url": cand_sj.source_job_url if cand_sj else None,
                    "similarity_score": c.similarity_score,
                    "matching_signals": c.matching_signals,
                    "review_status": c.review_status,
                }
            )

        items.append(
            {
                "id": g.id,
                "canonical_job_id": canon.id,
                "canonical_title": canon.title,
                "company_name": canon.company.name if canon.company else None,
                "canonical_location": canon.location_raw,
                "source_count": len(canon.source_jobs),
                "confidence": g.confidence,
                "resolution_status": g.resolution_status,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "candidates": cand_list,
            }
        )
    return {"total": len(items), "items": items}


@router.post("/duplicates/{group_id}/approve")
async def approve_duplicate_group(
    group_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    group = (
        await session.execute(
            select(DuplicateGroup)
            .where(DuplicateGroup.id == group_id)
            .options(selectinload(DuplicateGroup.candidates))
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Duplicate group not found.")

    now = datetime.now(timezone.utc)
    for cand in group.candidates:
        if cand.source_job_id and cand.candidate_job_id and cand.candidate_job_id != group.canonical_job_id:
            old_job_id = cand.candidate_job_id
            sj = await session.get(SourceJob, cand.source_job_id)
            if sj:
                sj.job_id = group.canonical_job_id
                sj.match_score = cand.similarity_score
                sj.match_reason = "manual_review_approved"
            old_job = await session.get(Job, old_job_id)
            if old_job:
                old_job.status = "CLOSED"
                old_job.closed_at = now
        cand.review_status = "APPROVED"
        cand.candidate_job_id = group.canonical_job_id

    group.resolution_status = "CONFIRMED"
    session.add(
        JobChange(
            job_id=group.canonical_job_id,
            change_type="MERGED",
            field_name="duplicate_group",
            old_value="PENDING_REVIEW",
            new_value="CONFIRMED",
            detected_at=now,
        )
    )
    await session.commit()
    return {"group_id": group.id, "resolution_status": "CONFIRMED"}


@router.post("/duplicates/{group_id}/reject")
async def reject_duplicate_group(
    group_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    group = (
        await session.execute(
            select(DuplicateGroup)
            .where(DuplicateGroup.id == group_id)
            .options(selectinload(DuplicateGroup.candidates))
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Duplicate group not found.")

    for cand in group.candidates:
        cand.review_status = "REJECTED"
    group.resolution_status = "REJECTED"
    await session.commit()
    return {"group_id": group.id, "resolution_status": "REJECTED"}


@router.post("/duplicates/{group_id}/unmerge")
async def unmerge_duplicate_endpoint(
    group_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        return await unmerge_duplicate_group(session, group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/changes")
async def list_job_changes(
    change_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = (
        select(JobChange)
        .join(Job, Job.id == JobChange.job_id)
        .where(Job.is_synthetic.is_(False))
        .options(selectinload(JobChange.job).selectinload(Job.company))
    )
    if change_type:
        stmt = stmt.where(JobChange.change_type == change_type.upper())

    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
    rows = (
        await session.execute(
            stmt.order_by(desc(JobChange.detected_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": ch.id,
                "job_id": ch.job_id,
                "job_title": ch.job.title if ch.job else None,
                "company_name": ch.job.company.name if (ch.job and ch.job.company) else None,
                "ingestion_run_id": ch.ingestion_run_id,
                "change_type": ch.change_type,
                "field_name": ch.field_name,
                "old_value": ch.old_value,
                "new_value": ch.new_value,
                "detected_at": ch.detected_at.isoformat() if ch.detected_at else None,
            }
            for ch in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total > 0 else 0,
    }


@router.post("/search/rebuild")
async def rebuild_search_index_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await get_search_coordinator().rebuild_index(session)


@router.post("/scheduler/tick")
async def manual_scheduler_tick(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    queue = WorkerTaskQueue()
    if not await queue.is_healthy():
        raise HTTPException(status_code=503, detail="Redis worker queue is currently unavailable.")
    enqueued = await schedule_due_sources(session, queue, batch_size=25)
    return {"enqueued_sources": enqueued}
