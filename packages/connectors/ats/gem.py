from __future__ import annotations

import re
from typing import Any

from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

GEM_RE = re.compile(
    r"(?:jobs\.gem\.com|api\.gem\.com/job_board/v0)/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


class GemConnector(BaseConnector):
    connector_key = "gem"
    platform_name = "Gem.com"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        m = GEM_RE.search(url)
        return m.group(1).strip("/") if m else None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://jobs.gem.com/{slug}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Gem.com job board '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Gem.com board slug from '{source.source_url}'")

        api_url = f"https://api.gem.com/job_board/v0/{slug}/job_posts"
        resp = await self.http.get(api_url, headers={"Accept": "application/json"}, rate_limit_rpm=source.rate_limit_rpm)
        raw_list = resp.json()
        if not isinstance(raw_list, list):
            raw_list = []

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(raw_list) > max_jobs:
            raw_list = raw_list[:max_jobs]
            is_complete = False

        payloads = []
        for item in raw_list:
            ext_id = str(item.get("id") or item.get("internal_job_id") or "")
            if not ext_id:
                continue
            job_url = str(item.get("absolute_url") or f"https://jobs.gem.com/{slug}/{ext_id}")
            payloads.append(RawJobPayload(external_job_id=ext_id, raw_data=item, source_url=job_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=None,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"api_url": api_url, "latency_ms": resp.latency_ms, "slug": slug},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        ext_id = str(raw_job.get("id") or raw_job.get("internal_job_id"))
        loc_obj = raw_job.get("location") or {}
        loc_name = loc_obj.get("name") if isinstance(loc_obj, dict) else str(loc_obj or "")

        depts = raw_job.get("departments") or []
        dept_name = depts[0].get("name") if isinstance(depts, list) and depts and isinstance(depts[0], dict) else None

        job_url = str(raw_job.get("absolute_url") or source.source_url)

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=raw_job.get("content") or raw_job.get("content_plain") or "",
            source_job_url=job_url,
            application_url=job_url,
            department=dept_name,
            location_raw=loc_name or None,
            employment_type_raw=raw_job.get("employment_type"),
            workplace_type_raw=raw_job.get("location_type"),
            original_posted_at=raw_job.get("first_published_at") or raw_job.get("created_at"),
        )
