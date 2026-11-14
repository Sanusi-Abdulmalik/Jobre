from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.models.entities import (
    Company,
    DuplicateGroup,
    IngestionRun,
    Job,
    JobChange,
    Platform,
    Source,
    SourceJob,
)
from app.services.platform_service import build_coverage_report
from apps.workers.queues.redis_queue import WorkerTaskQueue
from packages.common.config import get_settings
from packages.search.engine import SearchQueryParams, get_search_coordinator, serialize_job_summary

router = APIRouter(tags=["Public API"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    settings = get_settings()
    pg_ok = False
    try:
        await session.execute(text("SELECT 1"))
        pg_ok = True
    except Exception:
        pg_ok = False

    queue = WorkerTaskQueue()
    redis_ok = await queue.is_healthy()
    depths = await queue.queue_depths() if redis_ok else {"high": 0, "normal": 0, "low": 0, "dlq": 0}
    search_status = await get_search_coordinator().health_status()
    raw_dir = Path(settings.raw_storage_path)
    raw_ok = raw_dir.exists() and raw_dir.is_dir()

    return {
        "status": "healthy" if pg_ok else "degraded",
        "service": "Jobre Universal Job Board Indexer",
        "components": {
            "postgresql": {"healthy": pg_ok},
            "redis": {"healthy": redis_ok, "queues": depths},
            "search": search_status,
            "raw_storage": {"healthy": raw_ok, "backend": settings.raw_storage_backend, "path": str(raw_dir)},
        },
    }


@router.get("/stats")
async def system_stats(session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    total_platforms = int((await session.execute(select(func.count(Platform.id)))).scalar_one() or 0)
    verified_platforms = int(
        (await session.execute(select(func.count(Platform.id)).where(Platform.implementation_status == "VERIFIED"))).scalar_one()
        or 0
    )
    implemented_platforms = int(
        (
            await session.execute(
                select(func.count(Platform.id)).where(
                    Platform.implementation_status.in_(("IMPLEMENTED", "TESTED", "VERIFIED"))
                )
            )
        ).scalar_one()
        or 0
    )

    total_sources = int(
        (await session.execute(select(func.count(Source.id)).where(Source.is_test_fixture.is_(False)))).scalar_one() or 0
    )
    active_sources = int(
        (
            await session.execute(
                select(func.count(Source.id)).where(Source.is_test_fixture.is_(False), Source.status == "ACTIVE")
            )
        ).scalar_one()
        or 0
    )
    total_companies = int((await session.execute(select(func.count(Company.id)))).scalar_one() or 0)

    job_counts_row = (
        await session.execute(
            select(
                func.count(Job.id),
                func.sum(case((Job.status == "ACTIVE", 1), else_=0)),
                func.sum(case((Job.status == "POSSIBLY_CLOSED", 1), else_=0)),
                func.sum(case((Job.status == "CLOSED", 1), else_=0)),
            ).where(Job.is_synthetic.is_(False))
        )
    ).one()

    total_jobs = int(job_counts_row[0] or 0)
    active_jobs = int(job_counts_row[1] or 0)
    possibly_closed_jobs = int(job_counts_row[2] or 0)
    closed_jobs = int(job_counts_row[3] or 0)

    dup_groups = int(
        (
            await session.execute(
                select(func.count(DuplicateGroup.id)).where(
                    DuplicateGroup.resolution_status.in_(("AUTO_MERGED", "CONFIRMED", "PENDING_REVIEW"))
                )
            )
        ).scalar_one()
        or 0
    )
    pending_dup_reviews = int(
        (
            await session.execute(
                select(func.count(DuplicateGroup.id)).where(DuplicateGroup.resolution_status == "PENDING_REVIEW")
            )
        ).scalar_one()
        or 0
    )

    run_row = (
        await session.execute(
            select(
                func.count(IngestionRun.id),
                func.sum(case((IngestionRun.status == "SUCCEEDED", 1), else_=0)),
                func.sum(case((IngestionRun.status == "FAILED", 1), else_=0)),
                func.max(case((IngestionRun.status == "SUCCEEDED", IngestionRun.completed_at), else_=None)),
            )
            .join(Source, Source.id == IngestionRun.source_id)
            .where(Source.is_test_fixture.is_(False))
        )
    ).one()

    # Jobs by platform chart data
    by_plat_rows = (
        await session.execute(
            select(
                Platform.name,
                Platform.category,
                Platform.connector_key,
                func.count(func.distinct(Job.id)),
            )
            .join(Source, Source.platform_id == Platform.id)
            .join(SourceJob, SourceJob.source_id == Source.id)
            .join(Job, Job.id == SourceJob.job_id)
            .where(Source.is_test_fixture.is_(False), Job.is_synthetic.is_(False))
            .group_by(Platform.name, Platform.category, Platform.connector_key)
            .order_by(desc(func.count(func.distinct(Job.id))))
        )
    ).all()

    by_workplace_rows = (
        await session.execute(
            select(Job.workplace_type, func.count(Job.id))
            .where(Job.is_synthetic.is_(False), Job.status == "ACTIVE")
            .group_by(Job.workplace_type)
            .order_by(desc(func.count(Job.id)))
        )
    ).all()

    return {
        "total_required_platforms": total_platforms,
        "verified_platforms": verified_platforms,
        "implemented_platforms": implemented_platforms,
        "total_registered_sources": total_sources,
        "active_sources": active_sources,
        "total_companies": total_companies,
        "indexed_jobs": total_jobs,
        "active_jobs": active_jobs,
        "possibly_closed_jobs": possibly_closed_jobs,
        "closed_jobs": closed_jobs,
        "duplicate_groups": dup_groups,
        "pending_duplicate_reviews": pending_dup_reviews,
        "total_ingestion_runs": int(run_row[0] or 0),
        "successful_ingestion_runs": int(run_row[1] or 0),
        "failed_ingestion_runs": int(run_row[2] or 0),
        "last_successful_refresh": run_row[3].isoformat() if run_row[3] else None,
        "jobs_by_platform": [
            {"platform": r[0], "category": r[1], "connector_key": r[2], "jobs_count": int(r[3])}
            for r in by_plat_rows
        ],
        "jobs_by_workplace": [
            {"workplace_type": r[0], "count": int(r[1])} for r in by_workplace_rows
        ],
    }


@router.get("/jobs/search")
async def search_jobs(
    q: str | None = Query(default=None, description="Keyword, phrase, or fuzzy search query"),
    title: str | None = Query(default=None),
    company: str | None = Query(default=None),
    company_id: str | None = Query(default=None),
    location: str | None = Query(default=None),
    country: str | None = Query(default=None),
    employment_type: str | None = Query(default=None),
    workplace_type: str | None = Query(default=None),
    salary_min: float | None = Query(default=None, ge=0),
    salary_currency: str | None = Query(default=None),
    posted_within_days: int | None = Query(default=None, ge=1),
    status: str = Query(default="ACTIVE"),
    platform: str | None = Query(default=None),
    sort_by: str = Query(default="relevance"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    params = SearchQueryParams(
        q=q,
        title=title,
        company=company,
        company_id=company_id,
        location=location,
        country=country,
        employment_type=employment_type,
        workplace_type=workplace_type,
        salary_min=salary_min,
        salary_currency=salary_currency,
        posted_within_days=posted_within_days,
        status=status,
        platform=platform,
        include_synthetic=False,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
    )
    res = await get_search_coordinator().search(session, params)
    return {
        "items": res.items,
        "total": res.total,
        "page": res.page,
        "page_size": res.page_size,
        "total_pages": res.total_pages,
        "backend_used": res.backend_used,
        "latency_ms": res.latency_ms,
        "facets": res.facets,
    }


@router.get("/jobs")
async def list_jobs(
    q: str | None = Query(default=None),
    company: str | None = Query(default=None),
    company_id: str | None = Query(default=None),
    location: str | None = Query(default=None),
    country: str | None = Query(default=None),
    employment_type: str | None = Query(default=None),
    workplace_type: str | None = Query(default=None),
    salary_min: float | None = Query(default=None, ge=0),
    status: str = Query(default="ACTIVE"),
    platform: str | None = Query(default=None),
    sort_by: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await search_jobs(
        q=q,
        title=None,
        company=company,
        company_id=company_id,
        location=location,
        country=country,
        employment_type=employment_type,
        workplace_type=workplace_type,
        salary_min=salary_min,
        salary_currency=None,
        posted_within_days=None,
        status=status,
        platform=platform,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
        session=session,
    )


@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    job = (
        await session.execute(
            select(Job)
            .where(Job.id == job_id)
            .options(
                selectinload(Job.company),
                selectinload(Job.source_jobs).selectinload(SourceJob.source).selectinload(Source.platform),
                selectinload(Job.changes),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    summary = serialize_job_summary(job)
    sources_out = [
        {
            "id": sj.id,
            "source_id": sj.source_id,
            "source_name": sj.source.source_name if sj.source else "Unknown Source",
            "platform_name": sj.source.platform.name if (sj.source and sj.source.platform) else None,
            "platform_key": sj.source.platform.connector_key if (sj.source and sj.source.platform) else None,
            "external_job_id": sj.external_job_id,
            "source_job_url": sj.source_job_url,
            "application_url": sj.application_url,
            "title_at_source": sj.title_at_source,
            "location_at_source": sj.location_at_source,
            "salary_at_source": sj.salary_at_source,
            "match_score": sj.match_score,
            "match_reason": sj.match_reason,
            "source_status": sj.source_status,
            "first_seen_at": sj.first_seen_at.isoformat() if sj.first_seen_at else None,
            "last_seen_at": sj.last_seen_at.isoformat() if sj.last_seen_at else None,
            "last_checked_at": sj.last_checked_at.isoformat() if sj.last_checked_at else None,
        }
        for sj in job.source_jobs
    ]
    changes_out = [
        {
            "id": ch.id,
            "change_type": ch.change_type,
            "field_name": ch.field_name,
            "old_value": ch.old_value,
            "new_value": ch.new_value,
            "detected_at": ch.detected_at.isoformat() if ch.detected_at else None,
        }
        for ch in sorted(job.changes, key=lambda c: c.detected_at, reverse=True)[:30]
    ]

    return {
        **summary,
        "description": job.description,
        "description_text": job.description_text,
        "employment_type_raw": job.employment_type_raw,
        "workplace_type_raw": job.workplace_type_raw,
        "last_modified_at": job.last_modified_at.isoformat() if job.last_modified_at else None,
        "closed_at": job.closed_at.isoformat() if job.closed_at else None,
        "content_hash": job.content_hash,
        "sources": sources_out,
        "changes": changes_out,
    }


@router.get("/jobs/{job_id}/sources")
async def get_job_sources(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    detail = await get_job_detail(job_id, session)
    return {"job_id": job_id, "sources": detail["sources"]}


@router.get("/companies")
async def list_companies(
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    active_job_count = func.count(func.distinct(case((Job.status == "ACTIVE", Job.id), else_=None)))
    stmt = (
        select(
            Company,
            active_job_count.label("active_jobs"),
            func.count(func.distinct(Source.id)).label("source_count"),
        )
        .outerjoin(Job, (Job.company_id == Company.id) & (Job.is_synthetic.is_(False)))
        .outerjoin(Source, (Source.company_id == Company.id) & (Source.is_test_fixture.is_(False)))
        .group_by(Company.id)
    )
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q.strip()}%"))

    count_q = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_q)).scalar_one() or 0)

    rows = (
        await session.execute(
            stmt.order_by(desc("active_jobs"), Company.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = [
        {
            "id": comp.id,
            "name": comp.name,
            "normalized_name": comp.normalized_name,
            "website_url": comp.website_url,
            "active_jobs_count": int(act_jobs or 0),
            "sources_count": int(src_cnt or 0),
            "created_at": comp.created_at.isoformat() if comp.created_at else None,
        }
        for comp, act_jobs, src_cnt in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total > 0 else 0,
    }


@router.get("/companies/{company_id}")
async def get_company_detail(
    company_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    comp = (
        await session.execute(
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.sources).selectinload(Source.platform))
        )
    ).scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found.")

    jobs = (
        await session.execute(
            select(Job)
            .where(Job.company_id == company_id, Job.is_synthetic.is_(False))
            .options(
                selectinload(Job.company),
                selectinload(Job.source_jobs).selectinload(SourceJob.source).selectinload(Source.platform),
            )
            .order_by(desc(Job.status == "ACTIVE"), desc(Job.first_seen_at))
            .limit(100)
        )
    ).scalars().all()

    return {
        "id": comp.id,
        "name": comp.name,
        "normalized_name": comp.normalized_name,
        "website_url": comp.website_url,
        "description": comp.description,
        "sources": [
            {
                "id": s.id,
                "source_name": s.source_name,
                "source_url": s.source_url,
                "platform_name": s.platform.name if s.platform else None,
                "platform_key": s.platform.connector_key if s.platform else None,
                "status": s.status,
                "last_successful_sync_at": s.last_successful_sync_at.isoformat() if s.last_successful_sync_at else None,
            }
            for s in comp.sources
            if not s.is_test_fixture
        ],
        "jobs": [serialize_job_summary(j) for j in jobs],
    }


@router.get("/sources")
async def list_sources(
    status: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = (
        select(Source)
        .where(Source.is_test_fixture.is_(False))
        .options(selectinload(Source.company), selectinload(Source.platform))
    )
    if status:
        stmt = stmt.where(Source.status == status.upper())
    if platform:
        stmt = stmt.join(Platform, Platform.id == Source.platform_id).where(Platform.connector_key == platform.lower())

    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
    rows = (
        await session.execute(
            stmt.order_by(desc(Source.created_at)).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()

    # Active job count per source
    src_ids = [s.id for s in rows]
    sj_counts: dict[str, int] = {}
    if src_ids:
        cnt_rows = (
            await session.execute(
                select(SourceJob.source_id, func.count(SourceJob.id))
                .where(SourceJob.source_id.in_(src_ids), SourceJob.source_status == "ACTIVE")
                .group_by(SourceJob.source_id)
            )
        ).all()
        sj_counts = {r[0]: int(r[1]) for r in cnt_rows}

    items = [
        {
            "id": s.id,
            "source_name": s.source_name,
            "source_url": s.source_url,
            "board_token": s.board_token,
            "canonical_domain": s.canonical_domain,
            "source_type": s.source_type,
            "status": s.status,
            "priority": s.priority,
            "refresh_interval_minutes": s.refresh_interval_minutes,
            "discovery_method": s.discovery_method,
            "discovery_confidence": s.discovery_confidence,
            "company_id": s.company_id,
            "company_name": s.company.name if s.company else None,
            "platform_id": s.platform_id,
            "platform_name": s.platform.name if s.platform else None,
            "platform_key": s.platform.connector_key if s.platform else None,
            "platform_category": s.platform.category if s.platform else None,
            "active_jobs_count": sj_counts.get(s.id, 0),
            "consecutive_failures": s.consecutive_failures,
            "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
            "last_successful_sync_at": s.last_successful_sync_at.isoformat() if s.last_successful_sync_at else None,
            "next_sync_at": s.next_sync_at.isoformat() if s.next_sync_at else None,
        }
        for s in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total > 0 else 0,
    }


@router.get("/sources/{source_id}")
async def get_source_detail(
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    src = (
        await session.execute(
            select(Source)
            .where(Source.id == source_id)
            .options(selectinload(Source.company), selectinload(Source.platform))
        )
    ).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")

    runs = (
        await session.execute(
            select(IngestionRun)
            .where(IngestionRun.source_id == source_id)
            .order_by(desc(IngestionRun.started_at))
            .limit(20)
        )
    ).scalars().all()

    return {
        "id": src.id,
        "source_name": src.source_name,
        "source_url": src.source_url,
        "board_token": src.board_token,
        "canonical_domain": src.canonical_domain,
        "source_type": src.source_type,
        "status": src.status,
        "priority": src.priority,
        "discovery_method": src.discovery_method,
        "discovery_confidence": src.discovery_confidence,
        "company_name": src.company.name if src.company else None,
        "platform_name": src.platform.name if src.platform else None,
        "platform_key": src.platform.connector_key if src.platform else None,
        "last_checked_at": src.last_checked_at.isoformat() if src.last_checked_at else None,
        "last_successful_sync_at": src.last_successful_sync_at.isoformat() if src.last_successful_sync_at else None,
        "recent_runs": [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_ms": r.duration_ms,
                "jobs_discovered": r.jobs_discovered,
                "jobs_created": r.jobs_created,
                "jobs_updated": r.jobs_updated,
                "jobs_deduplicated": r.jobs_deduplicated,
                "error_summary": r.error_summary,
            }
            for r in runs
        ],
    }


@router.get("/platforms")
async def list_platforms(
    category: str | None = Query(default=None, description="ATS or JOB_BOARD"),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    report = await build_coverage_report(session)
    plats = report["platforms"]
    if category:
        plats = [p for p in plats if p["category"] == category.upper()]
    if status:
        plats = [p for p in plats if p["implementation_status"] == status.upper()]
    return {
        "total": len(plats),
        "status_summary": report["status_summary"],
        "category_breakdown": report["category_breakdown"],
        "items": plats,
    }


@router.get("/platforms/coverage")
async def get_platform_coverage(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await build_coverage_report(session)


@router.get("/platforms/coverage/export")
async def export_platform_coverage(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    report = await build_coverage_report(session)
    if format == "json":
        import orjson

        return Response(
            content=orjson.dumps(report, option=orjson.OPT_INDENT_2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="jobre-platform-coverage.json"'},
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "platform_name",
            "category",
            "connector_key",
            "implementation_status",
            "sources_discovered",
            "jobs_indexed",
            "active_jobs",
            "failed_requests",
            "last_successful_run",
            "example_source_url",
            "verification_run_id",
            "verified_at",
            "evidence_location",
            "extraction_method",
            "known_limitations",
        ]
    )
    for p in report["platforms"]:
        ev = p.get("verification_evidence") or {}
        writer.writerow(
            [
                p["name"],
                p["category"],
                p["connector_key"],
                p["implementation_status"],
                p["sources_discovered"],
                p["jobs_indexed"],
                p["active_jobs"],
                p["failed_requests"],
                p["last_successful_run"] or "",
                ev.get("example_source_url", ""),
                ev.get("verification_run_id", ""),
                ev.get("verified_at", ""),
                ev.get("evidence_location", ""),
                p["extraction_method"] or "",
                p["known_limitations"] or "",
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jobre-platform-coverage.csv"'},
    )
