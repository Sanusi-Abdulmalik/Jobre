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

PINPOINT_RE = re.compile(r"([a-z0-9-]+)\.pinpointhq\.com", re.I)


class PinpointConnector(BaseConnector):
    connector_key = "pinpoint"
    platform_name = "Pinpoint"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        m = PINPOINT_RE.search(url)
        if m and m.group(1).lower() not in ("www", "developers", "app"):
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
                canonical_source_url=f"https://{slug}.pinpointhq.com",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Pinpoint tenant '{slug}.pinpointhq.com'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Pinpoint subdomain from '{source.source_url}'")

        api_url = f"https://{slug}.pinpointhq.com/postings.json"
        resp = await self.http.get(api_url, headers={"Accept": "application/json"}, rate_limit_rpm=source.rate_limit_rpm)
        body = resp.json()
        items = body.get("data", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(items) > max_jobs:
            items = items[:max_jobs]
            is_complete = False

        payloads = []
        for item in items:
            ext_id = str(item.get("id") or "")
            if not ext_id:
                continue
            job_url = str(item.get("url") or f"https://{slug}.pinpointhq.com/postings/{ext_id}")
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
        ext_id = str(raw_job.get("id"))
        loc = raw_job.get("location") or {}
        city = loc.get("city") if isinstance(loc, dict) else None
        region = loc.get("province") if isinstance(loc, dict) else None
        loc_name = loc.get("name") if isinstance(loc, dict) else str(loc or "")

        job_obj = raw_job.get("job") or {}
        dept_obj = job_obj.get("department") if isinstance(job_obj, dict) else None
        dept = dept_obj.get("name") if isinstance(dept_obj, dict) else None

        desc_parts = [
            raw_job.get("description") or "",
            raw_job.get("key_responsibilities") or "",
            raw_job.get("skills_knowledge_expertise") or "",
            raw_job.get("benefits") or "",
        ]
        full_html = "\n".join([p for p in desc_parts if p]).strip()

        comp_min = raw_job.get("compensation_minimum")
        comp_max = raw_job.get("compensation_maximum")
        comp_cur = raw_job.get("compensation_currency")
        comp_freq = raw_job.get("compensation_frequency")
        comp_visible = raw_job.get("compensation_visible", True)

        job_url = str(raw_job.get("url") or source.source_url)

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=full_html,
            source_job_url=job_url,
            application_url=f"{job_url.rstrip('/')}/applications/new",
            department=dept,
            location_raw=loc_name or None,
            city=city,
            region=region,
            salary_min=comp_min if comp_visible else None,
            salary_max=comp_max if comp_visible else None,
            salary_currency=comp_cur if comp_visible else None,
            salary_period=comp_freq if comp_visible else None,
            employment_type_raw=raw_job.get("employment_type_text") or raw_job.get("employment_type"),
            workplace_type_raw=raw_job.get("workplace_type_text") or raw_job.get("workplace_type"),
            original_posted_at=raw_job.get(" created_at") or raw_job.get("deadline_at"),
        )
