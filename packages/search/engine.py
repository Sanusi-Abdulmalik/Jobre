from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import Select, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Company, Job, Platform, Source, SourceJob
from packages.common.config import PROJECT_ROOT, get_settings
from packages.common.metrics import SEARCH_LATENCY_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class SearchQueryParams:
    q: str | None = None
    title: str | None = None
    company: str | None = None
    company_id: str | None = None
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    salary_min: float | None = None
    salary_currency: str | None = None
    posted_within_days: int | None = None
    status: str = "ACTIVE"
    platform: str | None = None
    include_synthetic: bool = False
    page: int = 1
    page_size: int = 20
    sort_by: str = "relevance"  # relevance | newest | salary_desc | updated


@dataclass
class SearchResultPage:
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
    backend_used: str
    latency_ms: float
    facets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def serialize_job_summary(job: Job) -> dict[str, Any]:
    platforms_seen: list[str] = []
    platform_names: list[str] = []
    for sj in job.source_jobs:
        if sj.source and sj.source.platform:
            ck = sj.source.platform.connector_key
            pname = sj.source.platform.name
            if ck not in platforms_seen:
                platforms_seen.append(ck)
            if pname not in platform_names:
                platform_names.append(pname)

    return {
        "id": job.id,
        "canonical_job_key": job.canonical_job_key,
        "title": job.title,
        "company_id": job.company_id,
        "company_name": job.company.name if job.company else "Unknown",
        "department": job.department,
        "location_raw": job.location_raw,
        "city": job.city,
        "region": job.region,
        "country": job.country,
        "country_code": job.country_code,
        "salary_raw": job.salary_raw,
        "salary_min": float(job.salary_min) if job.salary_min is not None else None,
        "salary_max": float(job.salary_max) if job.salary_max is not None else None,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "employment_type": job.employment_type,
        "workplace_type": job.workplace_type,
        "primary_source_url": job.primary_source_url,
        "primary_application_url": job.primary_application_url,
        "original_posted_at": job.original_posted_at.isoformat() if job.original_posted_at else None,
        "first_seen_at": job.first_seen_at.isoformat() if job.first_seen_at else None,
        "last_seen_at": job.last_seen_at.isoformat() if job.last_seen_at else None,
        "last_checked_at": job.last_checked_at.isoformat() if job.last_checked_at else None,
        "status": job.status,
        "source_count": len(job.source_jobs),
        "platforms": platforms_seen,
        "platform_names": platform_names,
        "snippet": (job.description_text or "")[:280].strip(),
    }


class OpenSearchDriver:
    """Async OpenSearch projection client."""

    def __init__(self, url: str, index_name: str) -> None:
        self.url = url
        self.index_name = index_name
        self._mappings_path = PROJECT_ROOT / "infrastructure" / "opensearch" / "mappings.json"

    def _client(self) -> Any:
        from opensearchpy import AsyncOpenSearch

        return AsyncOpenSearch(hosts=[self.url], timeout=5, max_retries=1, retry_on_timeout=False)

    async def is_healthy(self) -> bool:
        client = self._client()
        try:
            health = await client.cluster.health()
            return health.get("status") in ("green", "yellow")
        except Exception:
            return False
        finally:
            await client.close()

    async def ensure_index(self) -> None:
        client = self._client()
        try:
            exists = await client.indices.exists(index=self.index_name)
            if not exists:
                body = json.loads(self._mappings_path.read_text(encoding="utf-8"))
                await client.indices.create(index=self.index_name, body=body)
        finally:
            await client.close()

    async def bulk_upsert(self, docs: list[dict[str, Any]]) -> int:
        if not docs:
            return 0
        await self.ensure_index()
        client = self._client()
        try:
            actions: list[dict[str, Any]] = []
            for doc in docs:
                actions.append({"index": {"_index": self.index_name, "_id": doc["id"]}})
                actions.append(doc)
            await client.bulk(body=actions, refresh=True)
            return len(docs)
        finally:
            await client.close()

    async def search(self, params: SearchQueryParams) -> tuple[list[str], int]:
        client = self._client()
        try:
            must: list[dict[str, Any]] = []
            filters: list[dict[str, Any]] = []

            if params.q:
                must.append(
                    {
                        "multi_match": {
                            "query": params.q,
                            "fields": ["title^3", "company_name^2", "location_raw^1.5", "description_text"],
                            "fuzziness": "AUTO",
                            "operator": "and",
                        }
                    }
                )
            if params.title:
                must.append({"match": {"title": {"query": params.title, "fuzziness": "AUTO"}}})
            if params.company:
                must.append({"match": {"company_name": {"query": params.company, "fuzziness": "AUTO"}}})
            if params.company_id:
                filters.append({"term": {"company_id": params.company_id}})
            if params.location:
                must.append({"match": {"location_raw": {"query": params.location, "fuzziness": "AUTO"}}})
            if params.country:
                filters.append(
                    {
                        "bool": {
                            "should": [
                                {"term": {"country_code": params.country.upper()}},
                                {"match": {"country": params.country}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                )
            if params.employment_type:
                filters.append({"term": {"employment_type": params.employment_type.upper()}})
            if params.workplace_type:
                filters.append({"term": {"workplace_type": params.workplace_type.upper()}})
            if params.salary_min is not None:
                filters.append({"range": {"salary_max": {"gte": params.salary_min}}})
            if params.status and params.status.upper() != "ALL":
                filters.append({"term": {"status": params.status.upper()}})
            if params.platform:
                filters.append({"term": {"platforms": params.platform.lower()}})

            sort_clause: list[Any]
            if params.sort_by == "newest":
                sort_clause = [{"original_posted_at": {"order": "desc", "missing": "_last"}}, {"first_seen_at": "desc"}]
            elif params.sort_by == "salary_desc":
                sort_clause = [{"salary_max": {"order": "desc", "missing": "_last"}}]
            elif params.sort_by == "updated":
                sort_clause = [{"last_seen_at": "desc"}]
            else:
                sort_clause = ["_score", {"first_seen_at": "desc"}]

            from_offset = max(0, (params.page - 1) * params.page_size)
            body = {
                "from": from_offset,
                "size": params.page_size,
                "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filters}},
                "sort": sort_clause,
            }
            res = await client.search(index=self.index_name, body=body)
            hits_meta = res.get("hits", {})
            total_val = hits_meta.get("total", 0)
            total = total_val.get("value", 0) if isinstance(total_val, dict) else int(total_val)
            ids = [h["_id"] for h in hits_meta.get("hits", [])]
            return ids, total
        finally:
            await client.close()


class SearchCoordinator:
    """
    Coordinates search indexing & querying across OpenSearch (when enabled & reachable)
    and PostgreSQL 17 Full-Text + Trigram Search (always-available source-of-truth fallback).
    Never allows a search-index failure to corrupt primary PostgreSQL job writes.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.opensearch_enabled = settings.opensearch_enabled
        self.os_driver = OpenSearchDriver(settings.opensearch_url, settings.opensearch_index)

    async def sync_jobs(self, session: AsyncSession, job_ids: list[str]) -> dict[str, Any]:
        if not job_ids:
            return {"synced": 0, "backend": "none"}

        now = datetime.now(timezone.utc)
        stmt = (
            select(Job)
            .where(Job.id.in_(job_ids))
            .options(
                selectinload(Job.company),
                selectinload(Job.source_jobs).selectinload(SourceJob.source).selectinload(Source.platform),
            )
        )
        rows = (await session.execute(stmt)).scalars().all()
        docs = [serialize_job_summary(j) | {"description_text": j.description_text} for j in rows]

        backend_used = "postgresql_fts"
        if self.opensearch_enabled:
            try:
                if await self.os_driver.is_healthy():
                    await self.os_driver.bulk_upsert(docs)
                    backend_used = "opensearch"
            except Exception as exc:
                logger.warning("OpenSearch sync degraded cleanly to PostgreSQL FTS: %s", exc)

        for j in rows:
            j.search_synced_at = now
        await session.flush()
        return {"synced": len(rows), "backend": backend_used}

    async def rebuild_index(self, session: AsyncSession) -> dict[str, Any]:
        stmt = select(Job.id).where(Job.is_synthetic.is_(False))
        all_ids = list((await session.execute(stmt)).scalars().all())
        total_synced = 0
        backend = "postgresql_fts"
        for i in range(0, len(all_ids), 200):
            batch_ids = all_ids[i : i + 200]
            res = await self.sync_jobs(session, batch_ids)
            total_synced += res["synced"]
            backend = res["backend"]
        await session.commit()
        return {"rebuilt_documents": total_synced, "backend": backend}

    def _apply_pg_filters(self, stmt: Select[Any], params: SearchQueryParams, is_pg: bool) -> tuple[Select[Any], Any]:
        rank_expr = None
        if not params.include_synthetic:
            stmt = stmt.where(Job.is_synthetic.is_(False))

        if params.status and params.status.upper() != "ALL":
            stmt = stmt.where(Job.status == params.status.upper())

        if params.company_id:
            stmt = stmt.where(Job.company_id == params.company_id)

        if params.company:
            comp_pat = f"%{params.company.strip()}%"
            stmt = stmt.where(Company.name.ilike(comp_pat))

        if params.title:
            title_pat = f"%{params.title.strip()}%"
            stmt = stmt.where(Job.title.ilike(title_pat))

        if params.location:
            loc_pat = f"%{params.location.strip()}%"
            stmt = stmt.where(
                or_(
                    Job.location_raw.ilike(loc_pat),
                    Job.city.ilike(loc_pat),
                    Job.region.ilike(loc_pat),
                    Job.country.ilike(loc_pat),
                )
            )

        if params.country:
            c_clean = params.country.strip()
            if len(c_clean) == 2:
                stmt = stmt.where(Job.country_code == c_clean.upper())
            else:
                stmt = stmt.where(
                    or_(
                        Job.country.ilike(f"%{c_clean}%"),
                        Job.country_code == c_clean.upper(),
                    )
                )

        if params.employment_type:
            stmt = stmt.where(Job.employment_type == params.employment_type.upper())

        if params.workplace_type:
            stmt = stmt.where(Job.workplace_type == params.workplace_type.upper())

        if params.salary_min is not None:
            stmt = stmt.where(
                or_(
                    Job.salary_max >= params.salary_min,
                    Job.salary_min >= params.salary_min,
                )
            )

        if params.salary_currency:
            stmt = stmt.where(Job.salary_currency == params.salary_currency.upper())

        if params.posted_within_days is not None and params.posted_within_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=params.posted_within_days)
            stmt = stmt.where(func.coalesce(Job.original_posted_at, Job.first_seen_at) >= cutoff)

        if params.platform:
            plat_subq = (
                select(SourceJob.job_id)
                .join(Source, Source.id == SourceJob.source_id)
                .join(Platform, Platform.id == Source.platform_id)
                .where(Platform.connector_key == params.platform.lower())
            )
            stmt = stmt.where(Job.id.in_(plat_subq))

        if params.q and params.q.strip():
            q_str = params.q.strip()
            q_like = f"%{q_str}%"
            if is_pg:
                ts_vec = (
                    func.setweight(func.to_tsvector("english", func.coalesce(Job.title, "")), text("'A'"))
                    .op("||")(func.setweight(func.to_tsvector("english", func.coalesce(Company.name, "")), text("'B'")))
                    .op("||")(func.setweight(func.to_tsvector("english", func.coalesce(Job.location_raw, "")), text("'C'")))
                    .op("||")(func.setweight(func.to_tsvector("english", func.coalesce(func.left(Job.description_text, 12000), "")), text("'D'")))
                )
                ts_q = func.websearch_to_tsquery("english", q_str)
                trgm_sim = func.word_similarity(q_str, Job.title)
                stmt = stmt.where(
                    or_(
                        ts_vec.op("@@")(ts_q),
                        Job.title.ilike(q_like),
                        Company.name.ilike(q_like),
                        trgm_sim >= 0.45,
                    )
                )
                rank_expr = func.ts_rank_cd(ts_vec, ts_q) + (trgm_sim * 0.5)
            else:
                stmt = stmt.where(
                    or_(
                        Job.title.ilike(q_like),
                        Company.name.ilike(q_like),
                        Job.description_text.ilike(q_like),
                        Job.location_raw.ilike(q_like),
                    )
                )

        return stmt, rank_expr

    async def _compute_facets(self, session: AsyncSession, include_synthetic: bool) -> dict[str, list[dict[str, Any]]]:
        base_filter = [Job.status == "ACTIVE"]
        if not include_synthetic:
            base_filter.append(Job.is_synthetic.is_(False))

        wp_rows = (
            await session.execute(
                select(Job.workplace_type, func.count(Job.id))
                .where(*base_filter)
                .group_by(Job.workplace_type)
                .order_by(desc(func.count(Job.id)))
            )
        ).all()

        emp_rows = (
            await session.execute(
                select(Job.employment_type, func.count(Job.id))
                .where(*base_filter)
                .group_by(Job.employment_type)
                .order_by(desc(func.count(Job.id)))
            )
        ).all()

        country_rows = (
            await session.execute(
                select(Job.country, Job.country_code, func.count(Job.id))
                .where(*base_filter, Job.country.is_not(None))
                .group_by(Job.country, Job.country_code)
                .order_by(desc(func.count(Job.id)))
                .limit(15)
            )
        ).all()

        plat_rows = (
            await session.execute(
                select(Platform.connector_key, Platform.name, func.count(func.distinct(SourceJob.job_id)))
                .join(Source, Source.platform_id == Platform.id)
                .join(SourceJob, SourceJob.source_id == Source.id)
                .join(Job, Job.id == SourceJob.job_id)
                .where(*base_filter)
                .group_by(Platform.connector_key, Platform.name)
                .order_by(desc(func.count(func.distinct(SourceJob.job_id))))
            )
        ).all()

        return {
            "workplace_types": [{"value": r[0], "count": r[1]} for r in wp_rows if r[0]],
            "employment_types": [{"value": r[0], "count": r[1]} for r in emp_rows if r[0]],
            "countries": [{"name": r[0], "code": r[1], "count": r[2]} for r in country_rows if r[0]],
            "platforms": [{"key": r[0], "name": r[1], "count": r[2]} for r in plat_rows],
        }

    async def search(self, session: AsyncSession, params: SearchQueryParams) -> SearchResultPage:
        t0 = time.perf_counter()
        page = max(1, params.page)
        page_size = max(1, min(100, params.page_size))
        params.page = page
        params.page_size = page_size

        # Attempt OpenSearch first if enabled
        if self.opensearch_enabled:
            try:
                if await self.os_driver.is_healthy():
                    hit_ids, total = await self.os_driver.search(params)
                    items: list[dict[str, Any]] = []
                    if hit_ids:
                        rows = (
                            await session.execute(
                                select(Job)
                                .where(Job.id.in_(hit_ids))
                                .options(
                                    selectinload(Job.company),
                                    selectinload(Job.source_jobs).selectinload(SourceJob.source).selectinload(Source.platform),
                                )
                            )
                        ).scalars().all()
                        by_id = {r.id: r for r in rows}
                        items = [serialize_job_summary(by_id[jid]) for jid in hit_ids if jid in by_id]
                    facets = await self._compute_facets(session, params.include_synthetic)
                    elapsed_s = time.perf_counter() - t0
                    SEARCH_LATENCY_SECONDS.labels(backend="opensearch").observe(elapsed_s)
                    total_pages = max(1, (total + page_size - 1) // page_size)
                    return SearchResultPage(
                        items=items,
                        total=total,
                        page=page,
                        page_size=page_size,
                        total_pages=total_pages,
                        backend_used="opensearch",
                        latency_ms=round(elapsed_s * 1000.0, 2),
                        facets=facets,
                    )
            except Exception as exc:
                logger.warning("OpenSearch query failed, serving seamlessly from PostgreSQL FTS: %s", exc)

        # PostgreSQL FTS + Trigram search
        bind = session.get_bind()
        is_pg = bind.dialect.name == "postgresql"

        base_stmt = select(Job).join(Company, Company.id == Job.company_id)
        filtered_stmt, rank_expr = self._apply_pg_filters(base_stmt, params, is_pg)

        count_stmt = select(func.count()).select_from(filtered_stmt.subquery())
        total = int((await session.execute(count_stmt)).scalar_one() or 0)

        if params.sort_by == "newest":
            ordered = filtered_stmt.order_by(
                desc(func.coalesce(Job.original_posted_at, Job.first_seen_at)),
                Job.id.asc(),
            )
        elif params.sort_by == "salary_desc":
            ordered = filtered_stmt.order_by(
                Job.salary_max.desc().nulls_last(),
                Job.first_seen_at.desc(),
                Job.id.asc(),
            )
        elif params.sort_by == "updated":
            ordered = filtered_stmt.order_by(Job.last_modified_at.desc(), Job.id.asc())
        elif rank_expr is not None:
            ordered = filtered_stmt.order_by(
                desc(rank_expr),
                desc(func.coalesce(Job.original_posted_at, Job.first_seen_at)),
                Job.id.asc(),
            )
        else:
            ordered = filtered_stmt.order_by(
                desc(func.coalesce(Job.original_posted_at, Job.first_seen_at)),
                Job.id.asc(),
            )

        offset = (page - 1) * page_size
        page_stmt = (
            ordered.offset(offset)
            .limit(page_size)
            .options(
                selectinload(Job.company),
                selectinload(Job.source_jobs).selectinload(SourceJob.source).selectinload(Source.platform),
            )
        )
        jobs = (await session.execute(page_stmt)).scalars().all()
        items = [serialize_job_summary(j) for j in jobs]
        facets = await self._compute_facets(session, params.include_synthetic)

        elapsed_s = time.perf_counter() - t0
        SEARCH_LATENCY_SECONDS.labels(backend="postgresql_fts").observe(elapsed_s)
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0

        return SearchResultPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            backend_used="postgresql_fts",
            latency_ms=round(elapsed_s * 1000.0, 2),
            facets=facets,
        )

    async def health_status(self) -> dict[str, Any]:
        os_healthy = await self.os_driver.is_healthy() if self.opensearch_enabled else False
        return {
            "opensearch_configured": self.opensearch_enabled,
            "opensearch_healthy": os_healthy,
            "active_backend": "opensearch" if (self.opensearch_enabled and os_healthy) else "postgresql_fts",
            "rebuildable_from_postgres": True,
        }


@lru_cache(maxsize=1)
def get_search_coordinator() -> SearchCoordinator:
    return SearchCoordinator()
