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
    extract_jsonld_job_posting,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

BREEZY_RE = re.compile(r"([a-z0-9-]+)\.breezy\.hr", re.I)


class BreezyHRConnector(BaseConnector):
    connector_key = "breezy_hr"
    platform_name = "Breezy HR"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 40

    def _extract_slug(self, url: str) -> str | None:
        m = BREEZY_RE.search(url)
        if m and m.group(1).lower() not in ("www", "app", "developer"):
            return m.group(1).lower()
        return None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://{slug}.breezy.hr",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Breezy HR subdomain '{slug}.breezy.hr'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _enrich_description(self, item: dict[str, Any], rpm: int) -> dict[str, Any]:
        if item.get("description"):
            return item
        url = item.get("url")
        if not url:
            return item
        try:
            resp = await self.http.get(str(url), headers={"Accept": "text/html"}, rate_limit_rpm=rpm)
            ld = extract_jsonld_job_posting(resp.text)
            if ld and ld.get("description"):
                return {**item, "description_html": ld.get("description")}
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
            raise ValueError(f"Cannot determine Breezy HR subdomain from '{source.source_url}'")

        api_url = f"https://{slug}.breezy.hr/json"
        resp = await self.http.get(api_url, headers={"Accept": "application/json"}, rate_limit_rpm=source.rate_limit_rpm)
        raw_list = resp.json()
        if not isinstance(raw_list, list):
            raw_list = []

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(raw_list) > max_jobs:
            raw_list = raw_list[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(4)

        async def _enrich(it: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self._enrich_description(it, max(source.rate_limit_rpm, 45))

        enriched = await asyncio.gather(*[_enrich(it) for it in raw_list[:20]]) + raw_list[20:]

        payloads = []
        for item in enriched:
            ext_id = str(item.get("id") or item.get("friendly_id") or "")
            if not ext_id:
                continue
            job_url = str(item.get("url") or f"https://{slug}.breezy.hr/p/{ext_id}")
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
        ext_id = str(raw_job.get("id") or raw_job.get("friendly_id"))
        loc = raw_job.get("location") or {}
        city = loc.get("city") if isinstance(loc, dict) else None
        state_obj = loc.get("state") if isinstance(loc, dict) else None
        region = state_obj.get("name") if isinstance(state_obj, dict) else (state_obj if isinstance(state_obj, str) else None)
        country_obj = loc.get("country") if isinstance(loc, dict) else None
        country = country_obj.get("name") if isinstance(country_obj, dict) else None
        country_code = country_obj.get("id") if isinstance(country_obj, dict) else None
        loc_raw = loc.get("name") if isinstance(loc, dict) else str(loc or "")

        is_remote = loc.get("is_remote") if isinstance(loc, dict) else False
        wp_raw = "Remote" if is_remote else None

        type_obj = raw_job.get("type") or {}
        emp_raw = type_obj.get("name") if isinstance(type_obj, dict) else str(type_obj or "")

        comp_obj = raw_job.get("company") or {}
        company_name = comp_obj.get("name") if isinstance(comp_obj, dict) and comp_obj.get("name") else source.company_name

        job_url = str(raw_job.get("url") or source.source_url)
        desc = raw_job.get("description_html") or raw_job.get("description") or raw_job.get("name") or ""

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("name") or "Untitled Role"),
            company_name=company_name,
            description_html_or_text=desc,
            source_job_url=job_url,
            application_url=f"{job_url.rstrip('/')}/apply",
            department=raw_job.get("department"),
            location_raw=loc_raw or None,
            city=city,
            region=region,
            country=country,
            country_code=country_code,
            salary_raw=raw_job.get("salary"),
            employment_type_raw=emp_raw,
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("published_date"),
        )
