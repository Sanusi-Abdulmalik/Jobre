from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

GH_SLUG_RE = re.compile(
    r"(?:job-)?boards\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
GH_API_RE = re.compile(
    r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


class GreenhouseConnector(BaseConnector):
    connector_key = "greenhouse"
    platform_name = "Greenhouse"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "for" in qs and qs["for"]:
            return qs["for"][0].strip()
        for pat in (GH_API_RE, GH_SLUG_RE):
            m = pat.search(url)
            if m:
                slug = m.group(1).strip()
                if slug.lower() not in ("embed", "v1", "boards"):
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
                canonical_source_url=f"https://boards.greenhouse.io/{slug}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Greenhouse board token '{slug}' in URL",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Greenhouse board token from '{source.source_url}'")

        api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        resp = await self.http.get(
            api_url,
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        data = resp.json()
        raw_list = data.get("jobs", []) if isinstance(data, dict) else []
        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(raw_list) > max_jobs:
            raw_list = raw_list[:max_jobs]
            is_complete = False

        payloads: list[RawJobPayload] = []
        for item in raw_list:
            ext_id = str(item.get("id") or item.get("internal_job_id") or "")
            if not ext_id:
                continue
            job_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{slug}/jobs/{ext_id}"
            payloads.append(
                RawJobPayload(
                    external_job_id=ext_id,
                    raw_data=item,
                    source_url=job_url,
                )
            )

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

        departments = raw_job.get("departments") or []
        dept_name = None
        if isinstance(departments, list) and departments:
            first_dept = departments[0]
            if isinstance(first_dept, dict):
                dept_name = first_dept.get("name")

        # Inspect metadata for employment type or workplace type or pay range if present
        emp_raw = None
        wp_raw = None
        salary_raw = None
        metadata = raw_job.get("metadata") or []
        if isinstance(metadata, list):
            for meta in metadata:
                if not isinstance(meta, dict):
                    continue
                mname = str(meta.get("name") or "").lower()
                mval = meta.get("value")
                if isinstance(mval, list):
                    mval = ", ".join(str(x) for x in mval if x)
                if not mval:
                    continue
                if "employment" in mname or "type" in mname:
                    emp_raw = str(mval)
                elif "workplace" in mname or "remote" in mname or "location type" in mname:
                    wp_raw = str(mval)
                elif "salary" in mname or "compensation" in mname or "pay" in mname:
                    salary_raw = str(mval)

        job_url = raw_job.get("absolute_url") or source.source_url
        company = raw_job.get("company_name") or source.company_name

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=company,
            description_html_or_text=raw_job.get("content") or "",
            source_job_url=job_url,
            application_url=job_url,
            department=dept_name,
            location_raw=loc_name or None,
            salary_raw=salary_raw,
            employment_type_raw=emp_raw,
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("first_published") or raw_job.get("updated_at"),
        )
