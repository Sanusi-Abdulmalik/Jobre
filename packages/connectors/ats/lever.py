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

LEVER_RE = re.compile(
    r"(?:jobs(?:\.eu)?\.lever\.co|api(?:\.eu)?\.lever\.co/v0/postings)/([a-zA-Z0-9._-]+)",
    re.IGNORECASE,
)


class LeverConnector(BaseConnector):
    connector_key = "lever"
    platform_name = "Lever.co"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug_and_region(self, url: str) -> tuple[str | None, bool]:
        is_eu = ".eu.lever.co" in url.lower()
        m = LEVER_RE.search(url)
        return (m.group(1).strip("/") if m else None), is_eu

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug, is_eu = self._extract_slug_and_region(source_url)
        if slug:
            host = "jobs.eu.lever.co" if is_eu else "jobs.lever.co"
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://{host}/{slug}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Lever postings board '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug_parsed, is_eu = self._extract_slug_and_region(source.source_url)
        slug = source.board_token or slug_parsed
        if not slug:
            raise ValueError(f"Cannot determine Lever board slug from '{source.source_url}'")

        skip = int(cursor) if cursor and cursor.isdigit() else 0
        page_size = int(source.extra_config.get("page_size", 100))
        api_host = "api.eu.lever.co" if is_eu else "api.lever.co"
        api_url = f"https://{api_host}/v0/postings/{slug}"

        resp = await self.http.get(
            api_url,
            params={"mode": "json", "skip": skip, "limit": page_size},
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        raw_list = resp.json()
        if not isinstance(raw_list, list):
            raw_list = []

        next_cursor = str(skip + page_size) if len(raw_list) == page_size else None
        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and (skip + len(raw_list)) >= max_jobs:
            raw_list = raw_list[: max(0, max_jobs - skip)]
            if next_cursor is not None:
                is_complete = False
                next_cursor = None

        payloads = [
            RawJobPayload(
                external_job_id=str(item.get("id")),
                raw_data=item,
                source_url=str(item.get("hostedUrl") or source.source_url),
            )
            for item in raw_list
            if item.get("id")
        ]

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=next_cursor,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"api_url": api_url, "skip": skip, "latency_ms": resp.latency_ms},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        cats = raw_job.get("categories") or {}
        lists_html = ""
        for section in raw_job.get("lists") or []:
            if isinstance(section, dict):
                lists_html += f"<h3>{section.get('text', '')}</h3><ul>{section.get('content', '')}</ul>"
        full_html = (
            f"{raw_job.get('description', '')}\n{lists_html}\n{raw_job.get('additional', '')}"
        ).strip()

        sal = raw_job.get("salaryRange") or {}
        hosted_url = str(raw_job.get("hostedUrl") or source.source_url)
        apply_url = str(raw_job.get("applyUrl") or hosted_url)

        return normalize_job_record(
            external_job_id=str(raw_job.get("id")),
            title=str(raw_job.get("text") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=full_html or raw_job.get("descriptionPlain") or "",
            source_job_url=hosted_url,
            application_url=apply_url,
            department=cats.get("department") or cats.get("team"),
            location_raw=cats.get("location"),
            country_code=raw_job.get("country"),
            salary_min=sal.get("min"),
            salary_max=sal.get("max"),
            salary_currency=sal.get("currency"),
            salary_period=sal.get("interval"),
            employment_type_raw=cats.get("commitment"),
            workplace_type_raw=raw_job.get("workplaceType"),
            original_posted_at=raw_job.get("createdAt"),
        )
