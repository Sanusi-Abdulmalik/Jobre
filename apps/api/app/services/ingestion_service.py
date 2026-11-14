from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import (
    Company,
    ConnectorHealth,
    CoverageEvidence,
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
from app.services.source_service import get_or_create_company
from packages.common.config import get_settings
from packages.common.http_client import HttpFetchError
from packages.common.metrics import DEDUP_DECISIONS_TOTAL, INGESTION_RUNS_TOTAL, JOBS_PROCESSED_TOTAL
from packages.common.raw_storage import RawSnapshotStore
from packages.common.security import canonicalize_url, sha256_hex
from packages.connectors.base import BaseConnector, ConnectorSourceConfig, RawJobPayload
from packages.connectors.registry import get_connector_registry
from packages.deduplication.engine import (
    CandidateJobSnapshot,
    DeduplicationOutcome,
    evaluate_duplicate_candidate,
)
from packages.lifecycle.engine import compute_field_diffs, evaluate_missing_job_transition
from packages.normalization.engine import NormalizedJobInput
from packages.search.engine import get_search_coordinator

logger = logging.getLogger(__name__)


class IngestionPipelineService:
    """
    Executes traceable, idempotent source ingestion runs:
    Lock -> Fetch -> Raw Storage -> Normalization -> Cross-Source Deduplication ->
    Change & Safe Closure Detection -> PostgreSQL Commit -> Search Index Sync.
    """

    def __init__(
        self,
        *,
        raw_store: RawSnapshotStore | None = None,
        connector_override: BaseConnector | None = None,
    ) -> None:
        self.settings = get_settings()
        self.raw_store = raw_store or RawSnapshotStore()
        self.registry = get_connector_registry()
        self.connector_override = connector_override
        self.search = get_search_coordinator()

    async def _acquire_source_lock(self, session: AsyncSession, source: Source) -> bool:
        now = datetime.now(timezone.utc)
        if source.sync_lock_until and source.sync_lock_until > now:
            return False
        source.sync_lock_until = now + timedelta(minutes=15)
        await session.commit()
        return True

    async def _release_source_lock(self, session: AsyncSession, source_id: str) -> None:
        src = await session.get(Source, source_id)
        if src:
            src.sync_lock_until = None
            await session.commit()

    async def _load_dedup_candidates(
        self,
        session: AsyncSession,
        company_id: str,
        norm_job: NormalizedJobInput,
        exclude_source_id: str,
    ) -> list[CandidateJobSnapshot]:
        canon_app = canonicalize_url(norm_job.application_url)
        filters = [Job.company_id == company_id]
        if canon_app:
            filters.append(Job.primary_application_url == norm_job.application_url)
            filters.append(Job.primary_source_url == norm_job.application_url)
            sj_url_subq = select(SourceJob.job_id).where(
                or_(
                    SourceJob.source_job_url == norm_job.application_url,
                    SourceJob.application_url == norm_job.application_url,
                )
            )
            filters.append(Job.id.in_(sj_url_subq))

        stmt = (
            select(Job)
            .where(or_(*filters), Job.status != "CLOSED")
            .options(selectinload(Job.company), selectinload(Job.source_jobs))
            .limit(80)
        )
        jobs = (await session.execute(stmt)).scalars().all()
        snapshots: list[CandidateJobSnapshot] = []
        for j in jobs:
            # Skip if this job is already linked to the exact same source (handled by source_jobs lookup)
            if any(sj.source_id == exclude_source_id for sj in j.source_jobs):
                continue
            snapshots.append(
                CandidateJobSnapshot(
                    job_id=j.id,
                    company_id=j.company_id,
                    normalized_company_name=j.company.normalized_name if j.company else norm_job.normalized_company_name,
                    title=j.title,
                    normalized_title=j.normalized_title,
                    description_text=j.description_text,
                    location_raw=j.location_raw,
                    city=j.city,
                    region=j.region,
                    country_code=j.country_code,
                    workplace_type=j.workplace_type,
                    primary_application_url=j.primary_application_url,
                    primary_source_url=j.primary_source_url,
                    known_external_ids=[sj.external_job_id for sj in j.source_jobs],
                    known_application_urls=[
                        u
                        for sj in j.source_jobs
                        for u in (sj.application_url, sj.source_job_url)
                        if u
                    ],
                    original_posted_at=j.original_posted_at,
                )
            )
        return snapshots

    async def _update_connector_health(
        self,
        session: AsyncSession,
        *,
        platform_id: str | None,
        succeeded: bool,
        latency_ms: float,
        error_msg: str | None = None,
    ) -> None:
        if not platform_id:
            return
        now = datetime.now(timezone.utc)
        health = (
            await session.execute(
                select(ConnectorHealth).where(
                    ConnectorHealth.platform_id == platform_id,
                    ConnectorHealth.source_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if health is None:
            health = ConnectorHealth(
                platform_id=platform_id,
                source_id=None,
                total_runs=0,
                failed_runs=0,
                consecutive_failures=0,
                average_response_time=0.0,
                error_rate=0.0,
            )
            session.add(health)

        health.total_runs += 1
        health.checked_at = now
        if succeeded:
            health.last_success_at = now
            health.consecutive_failures = 0
            prev_avg = health.average_response_time or latency_ms
            health.average_response_time = round((prev_avg * 0.7) + (latency_ms * 0.3), 2)
        else:
            health.failed_runs += 1
            health.consecutive_failures += 1
            health.last_failure_at = now
            health.last_error = (error_msg or "")[:1000]

        health.error_rate = round(health.failed_runs / max(1, health.total_runs), 4)
        if health.consecutive_failures >= 3:
            health.health_status = "FAILING"
        elif health.consecutive_failures >= 1 or health.error_rate > 0.35:
            health.health_status = "DEGRADED"
        else:
            health.health_status = "HEALTHY"

    async def execute_source_run(
        self,
        session: AsyncSession,
        source_id: str,
        *,
        trigger_type: str = "MANUAL",
        max_jobs_override: int | None = None,
        record_verification: bool = False,
    ) -> IngestionRun:
        source = (
            await session.execute(
                select(Source)
                .where(Source.id == source_id)
                .options(selectinload(Source.company), selectinload(Source.platform))
            )
        ).scalar_one_or_none()
        if source is None:
            raise ValueError(f"Source '{source_id}' not found.")

        connector_key = (
            self.connector_override.connector_key
            if self.connector_override
            else (source.platform.connector_key if source.platform else "unassigned")
        )

        # Acquire per-source lock
        locked = await self._acquire_source_lock(session, source)
        if not locked:
            skipped_run = IngestionRun(
                source_id=source.id,
                connector_id=connector_key,
                trigger_type=trigger_type,
                status="SKIPPED_LOCKED",
                is_complete_snapshot=False,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                duration_ms=0,
                error_summary="Skipped overlapping refresh: source lock is currently held.",
            )
            session.add(skipped_run)
            await session.commit()
            return skipped_run

        t0 = time.perf_counter()
        now = datetime.now(timezone.utc)
        run = IngestionRun(
            source_id=source.id,
            connector_id=connector_key,
            trigger_type=trigger_type,
            status="RUNNING",
            is_complete_snapshot=False,
            started_at=now,
        )
        session.add(run)
        await session.commit()

        touched_job_ids: set[str] = set()

        try:
            connector = self.connector_override or self.registry.get_connector(connector_key)
            extra_cfg = dict(source.source_config or {})
            if max_jobs_override is not None:
                extra_cfg["max_jobs"] = max_jobs_override

            src_cfg = ConnectorSourceConfig(
                source_id=source.id,
                source_name=source.source_name,
                source_url=source.source_url,
                company_name=source.company.name if source.company else source.source_name,
                board_token=source.board_token,
                rate_limit_rpm=source.platform.rate_limit_rpm if source.platform else 30,
                extra_config=extra_cfg,
            )

            # 1. Fetch all pages
            all_raw_payloads: list[RawJobPayload] = []
            cursor: str | None = None
            is_complete = True
            last_http_status = 200
            total_latency_ms = 0.0
            pages_fetched = 0

            while True:
                batch = await connector.fetch_jobs(src_cfg, cursor=cursor)
                pages_fetched += 1
                last_http_status = batch.http_status
                total_latency_ms += float(batch.request_metadata.get("latency_ms", 0.0))
                all_raw_payloads.extend(batch.jobs)
                if not batch.is_complete:
                    is_complete = False
                eff_max = extra_cfg.get("max_jobs")
                if isinstance(eff_max, int) and eff_max > 0 and len(all_raw_payloads) >= eff_max:
                    if batch.next_cursor or len(all_raw_payloads) > eff_max:
                        is_complete = False
                    all_raw_payloads = all_raw_payloads[:eff_max]
                    break
                if not batch.next_cursor or pages_fetched >= 25:
                    if batch.next_cursor and pages_fetched >= 25:
                        is_complete = False
                    break
                cursor = batch.next_cursor

            run.http_status = last_http_status
            run.jobs_discovered = len(all_raw_payloads)
            run.is_complete_snapshot = is_complete

            # Preload existing source_jobs for this source
            existing_sjs = (
                await session.execute(
                    select(SourceJob)
                    .where(SourceJob.source_id == source.id)
                    .options(selectinload(SourceJob.job))
                )
            ).scalars().all()
            sj_by_ext: dict[str, SourceJob] = {sj.external_job_id: sj for sj in existing_sjs}
            seen_ext_ids: set[str] = set()
            first_evidence_location: str | None = None

            # 2. Store Raw -> Normalize -> Deduplicate -> Lifecycle Update
            for raw_item in all_raw_payloads:
                seen_ext_ids.add(raw_item.external_job_id)
                storage_loc, raw_hash = self.raw_store.save_snapshot(
                    connector_key=connector.connector_key,
                    run_id=run.id,
                    external_job_id=raw_item.external_job_id,
                    payload=raw_item.raw_data,
                )
                if first_evidence_location is None:
                    first_evidence_location = storage_loc

                raw_rec = RawJobRecord(
                    source_id=source.id,
                    ingestion_run_id=run.id,
                    external_job_id=raw_item.external_job_id,
                    http_status=last_http_status,
                    payload=raw_item.raw_data,
                    content_hash=raw_hash,
                    storage_location=storage_loc,
                    fetched_at=datetime.now(timezone.utc),
                    extraction_version=connector.extraction_version,
                    processing_status="STORED",
                )
                session.add(raw_rec)
                await session.flush()

                try:
                    norm_job = connector.normalize(raw_item.raw_data, src_cfg)
                    raw_rec.processing_status = "NORMALIZED"
                except Exception as norm_exc:
                    raw_rec.processing_status = "FAILED"
                    run.errors_count += 1
                    logger.warning("Normalization failed for %s:%s: %s", connector_key, raw_item.external_job_id, norm_exc)
                    JOBS_PROCESSED_TOTAL.labels(connector=connector_key, outcome="normalization_failed").inc()
                    continue

                run.jobs_processed += 1
                obs_time = datetime.now(timezone.utc)

                # Resolve hiring company (especially important for multi-company job boards)
                if source.company and norm_job.normalized_company_name == source.company.normalized_name:
                    company_row = source.company
                else:
                    company_row = await get_or_create_company(session, norm_job.company_name)

                existing_sj = sj_by_ext.get(norm_job.external_job_id)
                if existing_sj is not None:
                    existing_sj.last_seen_at = obs_time
                    existing_sj.last_checked_at = obs_time
                    existing_sj.missing_runs_count = 0
                    existing_sj.source_status = "ACTIVE"
                    existing_sj.raw_job_id = raw_rec.id
                    existing_sj.source_job_url = norm_job.source_job_url
                    existing_sj.application_url = norm_job.application_url
                    existing_sj.title_at_source = norm_job.title
                    existing_sj.location_at_source = norm_job.location_raw
                    existing_sj.salary_at_source = norm_job.salary_raw

                    canon_job = existing_sj.job
                    canon_job.last_seen_at = obs_time
                    canon_job.last_checked_at = obs_time
                    canon_job.missing_consecutive_runs = 0

                    if canon_job.status in ("POSSIBLY_CLOSED", "CLOSED"):
                        prev_status = canon_job.status
                        canon_job.status = "ACTIVE"
                        canon_job.closed_at = None
                        session.add(
                            JobChange(
                                job_id=canon_job.id,
                                ingestion_run_id=run.id,
                                change_type="STATUS_TRANSITION",
                                field_name="status",
                                old_value=prev_status,
                                new_value="ACTIVE",
                                detected_at=obs_time,
                            )
                        )

                    if canon_job.content_hash != norm_job.content_hash:
                        diffs = compute_field_diffs(
                            {
                                "title": canon_job.title,
                                "description_text": canon_job.description_text,
                                "location_raw": canon_job.location_raw,
                                "salary_min": canon_job.salary_min,
                                "salary_max": canon_job.salary_max,
                                "salary_currency": canon_job.salary_currency,
                                "employment_type": canon_job.employment_type,
                                "workplace_type": canon_job.workplace_type,
                                "primary_application_url": canon_job.primary_application_url,
                            },
                            norm_job,
                        )
                        if diffs:
                            for d in diffs:
                                session.add(
                                    JobChange(
                                        job_id=canon_job.id,
                                        ingestion_run_id=run.id,
                                        change_type="FIELD_MODIFIED",
                                        field_name=d.field_name,
                                        old_value=d.old_value,
                                        new_value=d.new_value,
                                        detected_at=obs_time,
                                    )
                                )
                            canon_job.title = norm_job.title
                            canon_job.normalized_title = norm_job.normalized_title
                            canon_job.department = norm_job.department or canon_job.department
                            canon_job.description = norm_job.description
                            canon_job.description_text = norm_job.description_text
                            canon_job.location_raw = norm_job.location_raw
                            canon_job.city = norm_job.city
                            canon_job.region = norm_job.region
                            canon_job.country = norm_job.country
                            canon_job.country_code = norm_job.country_code
                            if norm_job.salary_min is not None or norm_job.salary_max is not None:
                                canon_job.salary_raw = norm_job.salary_raw
                                canon_job.salary_min = norm_job.salary_min
                                canon_job.salary_max = norm_job.salary_max
                                canon_job.salary_currency = norm_job.salary_currency
                                canon_job.salary_period = norm_job.salary_period
                            canon_job.employment_type = norm_job.employment_type
                            canon_job.workplace_type = norm_job.workplace_type
                            canon_job.primary_application_url = norm_job.application_url
                            canon_job.content_hash = norm_job.content_hash
                            canon_job.last_modified_at = obs_time
                            run.jobs_updated += 1
                            JOBS_PROCESSED_TOTAL.labels(connector=connector_key, outcome="updated").inc()

                    touched_job_ids.add(canon_job.id)
                    continue

                # New source_job: evaluate cross-source deduplication!
                candidates = await self._load_dedup_candidates(
                    session,
                    company_row.id,
                    norm_job,
                    exclude_source_id=source.id,
                )
                decision = evaluate_duplicate_candidate(
                    norm_job,
                    candidates,
                    auto_merge_threshold=self.settings.dedup_auto_merge_threshold,
                    review_threshold=self.settings.dedup_review_threshold,
                )
                DEDUP_DECISIONS_TOTAL.labels(decision=decision.outcome.value).inc()

                if decision.outcome == DeduplicationOutcome.AUTO_MERGE and decision.matched_job_id:
                    matched_job = await session.get(Job, decision.matched_job_id)
                    assert matched_job is not None
                    matched_job.last_seen_at = obs_time
                    matched_job.last_checked_at = obs_time

                    # Enrich missing compensation/metadata from secondary source without losing provenance
                    if matched_job.salary_min is None and norm_job.salary_min is not None:
                        matched_job.salary_raw = norm_job.salary_raw
                        matched_job.salary_min = norm_job.salary_min
                        matched_job.salary_max = norm_job.salary_max
                        matched_job.salary_currency = norm_job.salary_currency
                        matched_job.salary_period = norm_job.salary_period
                        session.add(
                            JobChange(
                                job_id=matched_job.id,
                                ingestion_run_id=run.id,
                                change_type="FIELD_MODIFIED",
                                field_name="salary_range",
                                old_value=None,
                                new_value=norm_job.salary_raw,
                                detected_at=obs_time,
                            )
                        )

                    new_sj = SourceJob(
                        job_id=matched_job.id,
                        source_id=source.id,
                        external_job_id=norm_job.external_job_id,
                        source_job_url=norm_job.source_job_url,
                        application_url=norm_job.application_url,
                        raw_job_id=raw_rec.id,
                        title_at_source=norm_job.title,
                        location_at_source=norm_job.location_raw,
                        salary_at_source=norm_job.salary_raw,
                        match_score=decision.score,
                        match_reason=decision.reason,
                        first_seen_at=obs_time,
                        last_seen_at=obs_time,
                        last_checked_at=obs_time,
                        source_status="ACTIVE",
                    )
                    session.add(new_sj)
                    await session.flush()
                    sj_by_ext[norm_job.external_job_id] = new_sj

                    dup_group = (
                        await session.execute(
                            select(DuplicateGroup).where(
                                DuplicateGroup.canonical_job_id == matched_job.id,
                                DuplicateGroup.resolution_status.in_(("AUTO_MERGED", "CONFIRMED")),
                            )
                        )
                    ).scalar_one_or_none()
                    if dup_group is None:
                        dup_group = DuplicateGroup(
                            canonical_job_id=matched_job.id,
                            confidence=decision.score,
                            resolution_status="AUTO_MERGED",
                        )
                        session.add(dup_group)
                        await session.flush()

                    session.add(
                        DuplicateCandidate(
                            duplicate_group_id=dup_group.id,
                            candidate_job_id=matched_job.id,
                            source_job_id=new_sj.id,
                            similarity_score=decision.score,
                            matching_signals=decision.signals | {"reason": decision.reason},
                            review_status="AUTO_LINKED",
                        )
                    )
                    run.jobs_deduplicated += 1
                    touched_job_ids.add(matched_job.id)
                    JOBS_PROCESSED_TOTAL.labels(connector=connector_key, outcome="deduplicated").inc()
                    continue

                # Create distinct canonical Job
                canon_key = sha256_hex(f"{source.id}:{norm_job.external_job_id}:{obs_time.timestamp()}")[:40]
                new_job = Job(
                    canonical_job_key=canon_key,
                    company_id=company_row.id,
                    title=norm_job.title,
                    normalized_title=norm_job.normalized_title,
                    department=norm_job.department,
                    description=norm_job.description,
                    description_text=norm_job.description_text,
                    location_raw=norm_job.location_raw,
                    city=norm_job.city,
                    region=norm_job.region,
                    country=norm_job.country,
                    country_code=norm_job.country_code,
                    salary_raw=norm_job.salary_raw,
                    salary_min=norm_job.salary_min,
                    salary_max=norm_job.salary_max,
                    salary_currency=norm_job.salary_currency,
                    salary_period=norm_job.salary_period,
                    employment_type=norm_job.employment_type,
                    employment_type_raw=norm_job.employment_type_raw,
                    workplace_type=norm_job.workplace_type,
                    workplace_type_raw=norm_job.workplace_type_raw,
                    primary_source_url=norm_job.source_job_url,
                    primary_application_url=norm_job.application_url,
                    original_posted_at=norm_job.original_posted_at,
                    first_seen_at=obs_time,
                    last_seen_at=obs_time,
                    last_checked_at=obs_time,
                    last_modified_at=obs_time,
                    status="ACTIVE",
                    is_synthetic=source.is_test_fixture,
                    content_hash=norm_job.content_hash,
                )
                session.add(new_job)
                await session.flush()

                new_sj = SourceJob(
                    job_id=new_job.id,
                    source_id=source.id,
                    external_job_id=norm_job.external_job_id,
                    source_job_url=norm_job.source_job_url,
                    application_url=norm_job.application_url,
                    raw_job_id=raw_rec.id,
                    title_at_source=norm_job.title,
                    location_at_source=norm_job.location_raw,
                    salary_at_source=norm_job.salary_raw,
                    match_score=1.0,
                    match_reason="primary_source",
                    first_seen_at=obs_time,
                    last_seen_at=obs_time,
                    last_checked_at=obs_time,
                    source_status="ACTIVE",
                )
                session.add(new_sj)
                await session.flush()
                sj_by_ext[norm_job.external_job_id] = new_sj

                if decision.outcome == DeduplicationOutcome.PENDING_REVIEW and decision.matched_job_id:
                    rev_group = DuplicateGroup(
                        canonical_job_id=decision.matched_job_id,
                        confidence=decision.score,
                        resolution_status="PENDING_REVIEW",
                    )
                    session.add(rev_group)
                    await session.flush()
                    session.add(
                        DuplicateCandidate(
                            duplicate_group_id=rev_group.id,
                            candidate_job_id=new_job.id,
                            source_job_id=new_sj.id,
                            similarity_score=decision.score,
                            matching_signals=decision.signals | {"reason": decision.reason},
                            review_status="PENDING_REVIEW",
                        )
                    )

                run.jobs_created += 1
                touched_job_ids.add(new_job.id)
                JOBS_PROCESSED_TOTAL.labels(connector=connector_key, outcome="created").inc()

            # 3. Evidence-based Closure Detection (ONLY on complete, successful snapshot!)
            if is_complete:
                check_time = datetime.now(timezone.utc)
                for ext_id, sj in sj_by_ext.items():
                    if ext_id in seen_ext_ids or sj.source_status == "CLOSED":
                        continue
                    run.jobs_missing += 1
                    sj.last_checked_at = check_time

                    # Count other active sources still advertising this canonical job
                    other_active = int(
                        (
                            await session.execute(
                                select(func.count(SourceJob.id)).where(
                                    SourceJob.job_id == sj.job_id,
                                    SourceJob.id != sj.id,
                                    SourceJob.source_status == "ACTIVE",
                                )
                            )
                        ).scalar_one()
                        or 0
                    )

                    canon_job = sj.job
                    prev_job_status = canon_job.status
                    tr = evaluate_missing_job_transition(
                        current_status=canon_job.status,
                        previous_missing_runs=sj.missing_runs_count,
                        run_succeeded=True,
                        is_complete_snapshot=True,
                        other_active_sources_count=other_active,
                        closure_threshold=self.settings.closure_missing_runs_threshold,
                    )
                    sj.missing_runs_count = tr.new_missing_runs
                    sj.source_status = (
                        "CLOSED"
                        if tr.new_missing_runs >= self.settings.closure_missing_runs_threshold
                        else "POSSIBLY_CLOSED"
                    )

                    canon_job.last_checked_at = check_time
                    canon_job.missing_consecutive_runs = tr.new_missing_runs
                    if tr.status_changed:
                        canon_job.status = tr.new_status
                        if tr.new_status == "CLOSED":
                            canon_job.closed_at = check_time
                            run.jobs_closed += 1
                        session.add(
                            JobChange(
                                job_id=canon_job.id,
                                ingestion_run_id=run.id,
                                change_type="STATUS_TRANSITION",
                                field_name="status",
                                old_value=prev_job_status,
                                new_value=tr.new_status,
                                detected_at=check_time,
                            )
                        )
                    touched_job_ids.add(canon_job.id)

            done_at = datetime.now(timezone.utc)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            run.status = "SUCCEEDED"
            run.completed_at = done_at
            run.duration_ms = duration_ms
            run.run_metadata = {
                "pages_fetched": pages_fetched,
                "total_http_latency_ms": round(total_latency_ms, 2),
                "is_complete_snapshot": is_complete,
            }

            source.last_checked_at = done_at
            source.last_successful_sync_at = done_at
            source.consecutive_failures = 0
            source.status = "ACTIVE"
            jitter_mins = random.randint(0, max(1, source.refresh_interval_minutes // 10))
            source.next_sync_at = done_at + timedelta(minutes=source.refresh_interval_minutes + jitter_mins)

            await self._update_connector_health(
                session,
                platform_id=source.platform_id,
                succeeded=True,
                latency_ms=total_latency_ms / max(1, pages_fetched),
            )

            # Record formal platform verification evidence if requested and valid jobs extracted
            if (
                record_verification
                and source.platform
                and not source.is_test_fixture
                and run.jobs_processed > 0
                and first_evidence_location
            ):
                source.platform.implementation_status = "VERIFIED"
                sample_ids = list(touched_job_ids)[:5]
                session.add(
                    CoverageEvidence(
                        platform_id=source.platform.id,
                        source_id=source.id,
                        verification_run_id=run.id,
                        verified_at=done_at,
                        evidence_type="LIVE_PUBLIC_EXTRACTION",
                        evidence_location=first_evidence_location,
                        sample_job_ids=sample_ids,
                        extracted_job_count=run.jobs_processed,
                        verification_status="VERIFIED",
                        notes=f"Verified live against {source.source_url} ({run.jobs_processed} normalized jobs).",
                    )
                )

            await session.commit()
            INGESTION_RUNS_TOTAL.labels(connector=connector_key, status="SUCCEEDED").inc()

            # 4. Synchronize search projection (fault-isolated from primary PostgreSQL commit!)
            if touched_job_ids:
                try:
                    await self.search.sync_jobs(session, list(touched_job_ids))
                    await session.commit()
                except Exception as search_exc:
                    logger.warning("Search index sync warning after run %s: %s", run.id, search_exc)

            return run

        except Exception as exc:
            await session.rollback()
            fail_time = datetime.now(timezone.utc)
            duration_ms = int((time.perf_counter() - t0) * 1000)

            run_ref = await session.get(IngestionRun, run.id)
            src_ref = await session.get(Source, source_id)
            http_code = exc.status_code if isinstance(exc, HttpFetchError) else None

            if run_ref:
                run_ref.status = "FAILED"
                run_ref.is_complete_snapshot = False
                run_ref.http_status = http_code
                run_ref.completed_at = fail_time
                run_ref.duration_ms = duration_ms
                run_ref.errors_count = (run_ref.errors_count or 0) + 1
                run_ref.error_summary = str(exc)[:1000]

            if src_ref:
                src_ref.last_checked_at = fail_time
                src_ref.consecutive_failures += 1
                if src_ref.consecutive_failures >= 3:
                    src_ref.status = "DEGRADED"
                backoff_mins = min(360, 15 * (2 ** min(src_ref.consecutive_failures, 5)))
                src_ref.next_sync_at = fail_time + timedelta(minutes=backoff_mins)
                await self._update_connector_health(
                    session,
                    platform_id=src_ref.platform_id,
                    succeeded=False,
                    latency_ms=float(duration_ms),
                    error_msg=str(exc),
                )

            await session.commit()
            INGESTION_RUNS_TOTAL.labels(connector=connector_key, status="FAILED").inc()
            assert run_ref is not None
            return run_ref

        finally:
            await self._release_source_lock(session, source_id)


async def unmerge_duplicate_group(session: AsyncSession, group_id: str) -> dict[str, Any]:
    """Unmerge an auto-merged or confirmed duplicate group, restoring independent canonical jobs."""
    group = (
        await session.execute(
            select(DuplicateGroup)
            .where(DuplicateGroup.id == group_id)
            .options(selectinload(DuplicateGroup.candidates))
        )
    ).scalar_one_or_none()
    if group is None:
        raise ValueError(f"Duplicate group '{group_id}' not found.")

    canon_job = await session.get(Job, group.canonical_job_id)
    if canon_job is None:
        raise ValueError("Canonical job for duplicate group no longer exists.")

    restored_job_ids: list[str] = []
    now = datetime.now(timezone.utc)

    for cand in group.candidates:
        if not cand.source_job_id:
            continue
        sj = await session.get(SourceJob, cand.source_job_id)
        if sj is None or sj.job_id != canon_job.id:
            continue

        new_key = sha256_hex(f"unmerged:{sj.id}:{now.timestamp()}")[:40]
        split_job = Job(
            canonical_job_key=new_key,
            company_id=canon_job.company_id,
            title=sj.title_at_source or canon_job.title,
            normalized_title=canon_job.normalized_title,
            department=canon_job.department,
            description=canon_job.description,
            description_text=canon_job.description_text,
            location_raw=sj.location_at_source or canon_job.location_raw,
            city=canon_job.city,
            region=canon_job.region,
            country=canon_job.country,
            country_code=canon_job.country_code,
            salary_raw=sj.salary_at_source or canon_job.salary_raw,
            employment_type=canon_job.employment_type,
            workplace_type=canon_job.workplace_type,
            primary_source_url=sj.source_job_url,
            primary_application_url=sj.application_url,
            first_seen_at=sj.first_seen_at,
            last_seen_at=sj.last_seen_at,
            last_checked_at=sj.last_checked_at,
            last_modified_at=now,
            status=sj.source_status,
            is_synthetic=canon_job.is_synthetic,
            content_hash=canon_job.content_hash,
        )
        session.add(split_job)
        await session.flush()

        sj.job_id = split_job.id
        sj.match_score = 1.0
        sj.match_reason = "unmerged_standalone"
        cand.candidate_job_id = split_job.id
        cand.review_status = "REJECTED"

        session.add(
            JobChange(
                job_id=canon_job.id,
                change_type="UNMERGED",
                field_name="duplicate_group",
                old_value=group.id,
                new_value=split_job.id,
                detected_at=now,
            )
        )
        restored_job_ids.append(split_job.id)

    group.resolution_status = "UNMERGED"
    await session.commit()
    return {"group_id": group.id, "status": "UNMERGED", "restored_job_ids": restored_job_ids}
