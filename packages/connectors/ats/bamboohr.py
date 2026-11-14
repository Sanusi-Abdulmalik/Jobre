from __future__ import annotations

import asyncio
import re
from typing import Any

from packages.common.http_client import HttpFetchError
from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

BAMBOO_RE = re.compile(r"([a-z0-9-]+)\.bamboohr\.com", re.I)


class BambooHRConnector(BaseConnector):
    connector_key = "bamboohr"
    platform_name = "BambooHR"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 30

    def _extract_slug(self, url: str) -> str | None:
        m = BAMBOO_RE.search(url)
        if m and m.group(1).lower() not in ("www", "documentation", "api"):
            return m.group(1).lower()
        return None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.97,
                board_token=slug,
                canonical_source_url=f"https://{slug}.bamboohr.com/careers",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched BambooHR careers portal '{slug}.bamboohr.com'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_detail(self, slug: str, item: dict[str, Any], rpm: int) -> dict[str, Any]:
        job_id = item.get("id")
        if not job_id:
            return item
        try:
            detail_url = f"https://{slug}.bamboohr.com/careers/{job_id}/detail"
            resp = await self.http.get(detail_url, headers={"Accept": "application/json"}, rate_limit_rpm=rpm)
            body = resp.json()
            if isinstance(body, dict) and isinstance(body.get("result"), dict):
                return {**item, **body["result"]}
        except Exception:
            pass
        return item

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine BambooHR subdomain from '{source.source_url}'")

        list_url = f"https://{slug}.bamboohr.com/careers/list"
        resp = await self.http.get(
            list_url,
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        if "application/json" not in resp.headers.get("content-type", ""):
            raise HttpFetchError(
                f"BambooHR portal '{slug}' did not return JSON from /careers/list",
                status_code=404,
                url=list_url,
                retryable=False,
                reason="not_bamboohr_json_portal",
            )
        body = resp.json()
        results = body.get("result", []) if isinstance(body, dict) else []

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(results) > max_jobs:
            results = results[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(4)

        async def _enrich(it: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self._fetch_detail(slug, it, max(source.rate_limit_rpm, 35))

        enriched = await asyncio.gather(*[_enrich(it) for it in results[:25]]) + results[25:]
        payloads = []
        for item in enriched:
            ext_id = str(item.get("id") or "")
            if not ext_id:
                continue
            job_url = f"https://{slug}.bamboohr.com/careers/{ext_id}"
            payloads.append(RawJobPayload(external_job_id=ext_id, raw_data=item, source_url=job_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=None,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"api_url": list_url, "latency_ms": resp.latency_ms, "slug": slug},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        slug = source.board_token or self._extract_slug(source.source_url) or ""
        ext_id = str(raw_job.get("id"))
        job_url = f"https://{slug}.bamboohr.com/careers/{ext_id}"

        loc = raw_job.get("location") or {}
        city = loc.get("city") if isinstance(loc, dict) else None
        region = loc.get("state") if isinstance(loc, dict) else None
        country = loc.get("country") if isinstance(loc, dict) else None

        wp_raw = None
        if raw_job.get("isRemote") is True:
            wp_raw = "Remote"
        elif raw_job.get("locationType") == "1":
            wp_raw = "Remote"
        elif raw_job.get("locationType") == "2":
            wp_raw = "Hybrid"

        job_opening = raw_job.get("jobOpening") or raw_job
        title = str(job_opening.get("jobOpeningName") or raw_job.get("jobOpeningName") or "Untitled Role")
        desc = job_opening.get("description") or raw_job.get("description") or title
        dept = job_opening.get("departmentLabel") or raw_job.get("departmentLabel")
        emp_type = job_opening.get("employmentStatusLabel") or raw_job.get("employmentStatusLabel")

        return normalize_job_record(
            external_job_id=ext_id,
            title=title,
            company_name=source.company_name,
            description_html_or_text=desc,
            source_job_url=job_url,
            application_url=job_url,
            department=dept,
            city=city,
            region=region,
            country=country,
            employment_type_raw=emp_type,
            workplace_type_raw=wp_raw,
            original_posted_at=job_opening.get("datePosted"),
        )
