from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    ConnectorHealth,
    CoverageEvidence,
    IngestionRun,
    Job,
    Platform,
    Source,
    SourceJob,
)
from packages.connectors.catalog import PLATFORM_CATALOG
from packages.connectors.registry import get_connector_registry


async def seed_platforms_catalog(session: AsyncSession) -> dict[str, int]:
    """Upsert all 78 required ATS and Job-Board platforms without downgrading VERIFIED/TESTED states."""
    registry = get_connector_registry()
    existing_rows = (await session.execute(select(Platform))).scalars().all()
    by_key = {p.connector_key: p for p in existing_rows}

    created = 0
    updated = 0
    preserved_states = {"VERIFIED", "TESTED", "DEGRADED", "DISABLED"}

    for spec in registry.all_platform_specs():
        plat = by_key.get(spec.connector_key)
        caps = {
            "url_patterns": list(spec.url_patterns),
            "html_signatures": list(spec.html_signatures),
            "connector_implemented": registry.has_connector(spec.connector_key),
        }
        if plat is None:
            plat = Platform(
                name=spec.name,
                category=spec.category,
                connector_key=spec.connector_key,
                implementation_status=spec.initial_status,
                discovery_method=spec.discovery_method,
                extraction_method=spec.extraction_method,
                auth_requirements=spec.auth_requirements,
                pagination_support=spec.pagination_support,
                rate_limit_rpm=spec.rate_limit_rpm,
                capabilities=caps,
                known_limitations=spec.known_limitations,
                documentation_url=spec.documentation_url,
            )
            session.add(plat)
            created += 1
        else:
            plat.name = spec.name
            plat.category = spec.category
            plat.discovery_method = spec.discovery_method
            plat.extraction_method = spec.extraction_method
            plat.auth_requirements = spec.auth_requirements
            plat.pagination_support = spec.pagination_support
            plat.rate_limit_rpm = spec.rate_limit_rpm
            plat.capabilities = caps
            plat.known_limitations = spec.known_limitations
            plat.documentation_url = spec.documentation_url
            if plat.implementation_status not in preserved_states:
                plat.implementation_status = spec.initial_status
            updated += 1

    await session.commit()
    return {"created": created, "updated": updated, "total": len(PLATFORM_CATALOG)}


async def build_coverage_report(session: AsyncSession) -> dict[str, Any]:
    """Generate real, evidence-backed coverage matrix across all 78 required platforms."""
    platforms = (
        await session.execute(
            select(Platform).order_by(Platform.category.asc(), Platform.name.asc())
        )
    ).scalars().all()

    # Source counts per platform (excluding test fixtures)
    src_counts = dict(
        (
            await session.execute(
                select(Source.platform_id, func.count(Source.id))
                .where(Source.is_test_fixture.is_(False))
                .group_by(Source.platform_id)
            )
        ).all()
    )

    # Job counts (total & active) per platform (excluding synthetic)
    job_stats_rows = (
        await session.execute(
            select(
                Source.platform_id,
                func.count(func.distinct(Job.id)),
                func.count(func.distinct(case((Job.status == "ACTIVE", Job.id), else_=None))),
            )
            .join(SourceJob, SourceJob.source_id == Source.id)
            .join(Job, Job.id == SourceJob.job_id)
            .where(Source.is_test_fixture.is_(False), Job.is_synthetic.is_(False))
            .group_by(Source.platform_id)
        )
    ).all()
    jobs_by_plat = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in job_stats_rows}

    # Run statistics per connector_key
    run_rows = (
        await session.execute(
            select(
                IngestionRun.connector_id,
                func.max(case((IngestionRun.status == "SUCCEEDED", IngestionRun.completed_at), else_=None)),
                func.max(case((IngestionRun.status == "FAILED", IngestionRun.completed_at), else_=None)),
                func.sum(case((IngestionRun.status == "FAILED", 1), else_=0)),
            )
            .join(Source, Source.id == IngestionRun.source_id)
            .where(Source.is_test_fixture.is_(False))
            .group_by(IngestionRun.connector_id)
        )
    ).all()
    runs_by_conn = {
        r[0]: {
            "last_success": r[1],
            "last_failure": r[2],
            "failed_requests": int(r[3] or 0),
        }
        for r in run_rows
    }

    # Latest verification evidence per platform
    ev_rows = (
        await session.execute(
            select(CoverageEvidence, Source.source_name, Source.source_url)
            .join(Source, Source.id == CoverageEvidence.source_id)
            .order_by(desc(CoverageEvidence.verified_at))
        )
    ).all()
    latest_ev: dict[str, dict[str, Any]] = {}
    for ev, src_name, src_url in ev_rows:
        if ev.platform_id not in latest_ev:
            latest_ev[ev.platform_id] = {
                "verification_run_id": ev.verification_run_id,
                "verified_at": ev.verified_at.isoformat() if ev.verified_at else None,
                "example_source_name": src_name,
                "example_source_url": src_url,
                "evidence_type": ev.evidence_type,
                "evidence_location": ev.evidence_location,
                "extracted_job_count": ev.extracted_job_count,
                "sample_job_ids": ev.sample_job_ids,
                "notes": ev.notes,
            }

    health_rows = (
        await session.execute(
            select(ConnectorHealth).where(ConnectorHealth.source_id.is_(None))
        )
    ).scalars().all()
    health_by_plat = {h.platform_id: h for h in health_rows}

    items: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    category_breakdown: dict[str, dict[str, int]] = {
        "ATS": {"total": 0, "verified": 0, "implemented": 0},
        "JOB_BOARD": {"total": 0, "verified": 0, "implemented": 0},
    }

    for p in platforms:
        st = p.implementation_status
        status_counts[st] = status_counts.get(st, 0) + 1
        cat_bucket = category_breakdown.setdefault(p.category, {"total": 0, "verified": 0, "implemented": 0})
        cat_bucket["total"] += 1
        if st == "VERIFIED":
            cat_bucket["verified"] += 1
        if st in ("IMPLEMENTED", "TESTED", "VERIFIED"):
            cat_bucket["implemented"] += 1

        total_jobs, active_jobs = jobs_by_plat.get(p.id, (0, 0))
        r_stat = runs_by_conn.get(p.connector_key, {})
        h_row = health_by_plat.get(p.id)

        items.append(
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "connector_key": p.connector_key,
                "implementation_status": st,
                "discovery_method": p.discovery_method,
                "extraction_method": p.extraction_method,
                "auth_requirements": p.auth_requirements,
                "pagination_support": p.pagination_support,
                "rate_limit_rpm": p.rate_limit_rpm,
                "last_successful_run": r_stat.get("last_success").isoformat() if r_stat.get("last_success") else None,
                "last_failed_run": r_stat.get("last_failure").isoformat() if r_stat.get("last_failure") else None,
                "sources_discovered": int(src_counts.get(p.id, 0)),
                "jobs_indexed": total_jobs,
                "active_jobs": active_jobs,
                "failed_requests": r_stat.get("failed_requests", 0),
                "health_status": h_row.health_status if h_row else "UNCHECKED",
                "average_response_time_ms": round(h_row.average_response_time, 2) if h_row else 0.0,
                "verification_evidence": latest_ev.get(p.id),
                "known_limitations": p.known_limitations,
                "documentation_url": p.documentation_url,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_required_platforms": len(platforms),
        "status_summary": status_counts,
        "category_breakdown": category_breakdown,
        "platforms": items,
    }
