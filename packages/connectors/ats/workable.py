from __future__ import annotations

import asyncio
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

WORKABLE_RE = re.compile(r"apply\.workable\.com/(?:api/v\d/accounts/)?([a-zA-Z0-9_-]+)", re.I)


class WorkableConnector(BaseConnector):
    connector_key = "workable"
    platform_name = "Workable"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 45

    def _extract_slug(self, url: str) -> str | None:
        m = WORKABLE_RE.search(url)
        if m:
            slug = m.group(1)
            if slug.lower() not in ("api", "j"):
                return slug
        return None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://apply.workable.com/{slug}/",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Workable account slug '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_detail(self, slug: str, item: dict[str, Any], rpm: int) -> dict[str, Any]:
        shortcode = item.get("shortcode")
        if not shortcode:
            return item
        try:
            detail_url = f"https://apply.workable.com/api/v2/accounts/{slug}/jobs/{shortcode}"
            resp = await self.http.get(detail_url, headers={"Accept": "application/json"}, rate_limit_rpm=rpm)
            detail = resp.json()
            if isinstance(detail, dict):
                return {**item, **detail}
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
            raise ValueError(f"Cannot determine Workable account slug from '{source.source_url}'")

        api_url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
        body: dict[str, Any] = {
            "query": "",
            "location": [],
            "department": [],
            "worktype": [],
            "remote": [],
        }
        if cursor:
            body["token"] = cursor

        resp = await self.http.post(
            api_url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json_body=body,
            rate_limit_rpm=source.rate_limit_rpm,
        )
        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        next_page = data.get("nextPage") if isinstance(data, dict) else None

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(results) >= max_jobs:
            results = results[:max_jobs]
            if next_page:
                next_page = None
                is_complete = False

        sem = asyncio.Semaphore(4)

        async def _enrich(it: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self._fetch_detail(slug, it, max(source.rate_limit_rpm, 45))

        enriched = await asyncio.gather(*[_enrich(it) for it in results])

        payloads = []
        for item in enriched:
            shortcode = str(item.get("shortcode") or item.get("id") or "")
            if not shortcode:
                continue
            job_url = f"https://apply.workable.com/{slug}/j/{shortcode}/"
            payloads.append(RawJobPayload(external_job_id=shortcode, raw_data=item, source_url=job_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=next_page,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"api_url": api_url, "latency_ms": resp.latency_ms, "slug": slug},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        slug = source.board_token or self._extract_slug(source.source_url) or ""
        shortcode = str(raw_job.get("shortcode") or raw_job.get("id"))
        job_url = f"https://apply.workable.com/{slug}/j/{shortcode}/"

        loc = raw_job.get("location") or {}
        city = loc.get("city")
        region = loc.get("region")
        country = loc.get("country")
        country_code = loc.get("countryCode")
        loc_raw = ", ".join([p for p in (city, region, country) if p]) or None

        desc_parts = [
            raw_job.get("description") or "",
            f"<h3>Requirements</h3>{raw_job['requirements']}" if raw_job.get("requirements") else "",
            f"<h3>Benefits</h3>{raw_job['benefits']}" if raw_job.get("benefits") else "",
        ]
        full_desc = "\n".join([p for p in desc_parts if p]).strip()

        dept_list = raw_job.get("department")
        dept = dept_list[0] if isinstance(dept_list, list) and dept_list else (dept_list if isinstance(dept_list, str) else None)

        wp_raw = raw_job.get("workplace") or ("Remote" if raw_job.get("remote") is True else None)

        return normalize_job_record(
            external_job_id=shortcode,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=full_desc,
            source_job_url=job_url,
            application_url=f"{job_url}apply/",
            department=dept,
            location_raw=loc_raw,
            city=city,
            region=region,
            country=country,
            country_code=country_code,
            employment_type_raw=raw_job.get("type") or raw_job.get("employment_type"),
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("published"),
        )
