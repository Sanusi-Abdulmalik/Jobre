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

RECRUITEE_RE = re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.I)


class RecruiteeConnector(BaseConnector):
    connector_key = "recruitee"
    platform_name = "Recruitee"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        m = RECRUITEE_RE.search(url)
        if m:
            sub = m.group(1).lower()
            if sub not in ("www", "app", "docs", "api"):
                return sub
        return None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://{slug}.recruitee.com",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Recruitee career subdomain '{slug}.recruitee.com'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Recruitee subdomain from '{source.source_url}'")

        api_url = f"https://{slug}.recruitee.com/api/offers/"
        resp = await self.http.get(
            api_url,
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        data = resp.json()
        offers = data.get("offers", []) if isinstance(data, dict) else []
        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(offers) > max_jobs:
            offers = offers[:max_jobs]
            is_complete = False

        payloads = []
        for offer in offers:
            ext_id = str(offer.get("id") or offer.get("slug") or "")
            if not ext_id:
                continue
            job_url = offer.get("careers_url") or f"https://{slug}.recruitee.com/o/{offer.get('slug', ext_id)}"
            payloads.append(RawJobPayload(external_job_id=ext_id, raw_data=offer, source_url=job_url))

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
        ext_id = str(raw_job.get("id") or raw_job.get("slug"))
        job_url = raw_job.get("careers_url") or source.source_url
        apply_url = raw_job.get("careers_apply_url") or f"{job_url.rstrip('/')}/c/new"

        desc_html = f"{raw_job.get('description') or ''}\n{raw_job.get('requirements') or ''}".strip()

        sal = raw_job.get("salary") or {}
        s_min = sal.get("min") if isinstance(sal, dict) else raw_job.get("min_salary")
        s_max = sal.get("max") if isinstance(sal, dict) else raw_job.get("max_salary")
        s_cur = sal.get("currency") if isinstance(sal, dict) else raw_job.get("salary_currency")
        s_period = sal.get("period") if isinstance(sal, dict) else raw_job.get("salary_period")

        wp_raw = None
        if raw_job.get("remote") is True:
            wp_raw = "Remote"
        elif raw_job.get("hybrid") is True:
            wp_raw = "Hybrid"
        elif raw_job.get("on_site") is True:
            wp_raw = "On-site"

        company = raw_job.get("company_name") or source.company_name

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=company,
            description_html_or_text=desc_html,
            source_job_url=job_url,
            application_url=apply_url,
            department=raw_job.get("department"),
            location_raw=raw_job.get("location"),
            city=raw_job.get("city"),
            region=raw_job.get("state_name") or raw_job.get("state_code"),
            country=raw_job.get("country"),
            country_code=raw_job.get("country_code"),
            salary_min=s_min,
            salary_max=s_max,
            salary_currency=s_cur,
            salary_period=s_period,
            employment_type_raw=raw_job.get("employment_type_code"),
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("published_at") or raw_job.get("created_at"),
        )
