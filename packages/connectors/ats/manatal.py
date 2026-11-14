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

MANATAL_PATH_RE = re.compile(r"careers-page\.com/(?:api/v1\.0/c/)?([a-zA-Z0-9_-]+)", re.I)
MANATAL_SUB_RE = re.compile(r"([a-zA-Z0-9_-]+)\.careers-page\.com", re.I)


class ManatalConnector(BaseConnector):
    connector_key = "manatal"
    platform_name = "Manatal"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 45

    def _extract_slug(self, url: str) -> str | None:
        m_sub = MANATAL_SUB_RE.search(url)
        if m_sub and m_sub.group(1).lower() not in ("www", "api", "app"):
            return m_sub.group(1).lower()
        m_path = MANATAL_PATH_RE.search(url)
        if m_path and m_path.group(1).lower() not in ("api", "jobs", "v1"):
            return m_path.group(1)
        return None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://www.careers-page.com/{slug}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Manatal careers-page.com slug '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Manatal career-page slug from '{source.source_url}'")

        page = int(cursor) if cursor and cursor.isdigit() else 1
        api_url = f"https://www.careers-page.com/api/v1.0/c/{slug}/jobs/"
        resp = await self.http.get(
            api_url,
            params={"page": page, "page_size": 25},
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        has_next = bool(data.get("next")) if isinstance(data, dict) else False
        next_cursor = str(page + 1) if has_next else None

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and (page * 25) >= max_jobs and has_next:
            next_cursor = None
            is_complete = False

        payloads = []
        for item in results:
            job_hash = str(item.get("hash") or item.get("id") or "")
            if not job_hash:
                continue
            job_url = f"https://www.careers-page.com/{slug}/job/{job_hash}"
            payloads.append(RawJobPayload(external_job_id=job_hash, raw_data=item, source_url=job_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=next_cursor,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"api_url": api_url, "page": page, "latency_ms": resp.latency_ms},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        slug = source.board_token or self._extract_slug(source.source_url) or ""
        job_hash = str(raw_job.get("hash") or raw_job.get("id"))
        job_url = f"https://www.careers-page.com/{slug}/job/{job_hash}"

        city = raw_job.get("city")
        region = raw_job.get("state")
        country = raw_job.get("country")
        loc_display = raw_job.get("location_display") or ", ".join([p for p in (city, region, country) if p]) or None

        wp_raw = None
        if raw_job.get("is_remote") is True:
            wp_raw = "Remote"
        elif raw_job.get("remote_type"):
            wp_raw = str(raw_job.get("remote_type"))

        s_min = raw_job.get("salary_min") if raw_job.get("is_salary_visible") is not False else None
        s_max = raw_job.get("salary_max") if raw_job.get("is_salary_visible") is not False else None

        return normalize_job_record(
            external_job_id=job_hash,
            title=str(raw_job.get("position_name") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=raw_job.get("description") or "",
            source_job_url=job_url,
            application_url=f"{job_url}/apply",
            department=raw_job.get("department"),
            location_raw=loc_display,
            city=city,
            region=region,
            country=country,
            salary_min=s_min,
            salary_max=s_max,
            salary_currency=raw_job.get("currency"),
            salary_period=raw_job.get("frequency"),
            employment_type_raw=raw_job.get("contract_details"),
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("published_at") or raw_job.get("created_at"),
        )
