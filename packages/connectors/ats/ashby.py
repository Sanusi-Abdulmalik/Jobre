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

ASHBY_RE = re.compile(
    r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/([a-zA-Z0-9._%-]+)",
    re.IGNORECASE,
)


class AshbyConnector(BaseConnector):
    connector_key = "ashby"
    platform_name = "Ashby"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        m = ASHBY_RE.search(url)
        return m.group(1).strip("/") if m else None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://jobs.ashbyhq.com/{slug}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Ashby job board slug '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Ashby board slug from '{source.source_url}'")

        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
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
            if item.get("isListed") is False:
                continue
            ext_id = str(item.get("id") or "")
            if not ext_id:
                continue
            job_url = item.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{ext_id}"
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
        ext_id = str(raw_job.get("id"))
        slug = source.board_token or self._extract_slug(source.source_url) or ""
        job_url = raw_job.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{ext_id}"
        apply_url = raw_job.get("applyUrl") or f"{job_url}/application"

        addr = (raw_job.get("address") or {}).get("postalAddress") or {}
        city = addr.get("addressLocality")
        region = addr.get("addressRegion")
        country = addr.get("addressCountry")

        comp = raw_job.get("compensation") or {}
        salary_raw = comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary")
        s_min = None
        s_max = None
        s_cur = None
        s_period = None
        summary_comps = comp.get("summaryComponents") or []
        for comp_item in summary_comps:
            if isinstance(comp_item, dict) and comp_item.get("compensationType") == "Salary":
                s_min = comp_item.get("minValue")
                s_max = comp_item.get("maxValue")
                s_cur = comp_item.get("currencyCode")
                s_period = comp_item.get("interval")
                break

        wp_raw = raw_job.get("workplaceType")
        if not wp_raw and raw_job.get("isRemote") is True:
            wp_raw = "Remote"

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=raw_job.get("descriptionHtml") or raw_job.get("descriptionPlain") or "",
            source_job_url=job_url,
            application_url=apply_url,
            department=raw_job.get("department") or raw_job.get("team"),
            location_raw=raw_job.get("location"),
            city=city,
            region=region,
            country=country,
            salary_raw=salary_raw,
            salary_min=s_min,
            salary_max=s_max,
            salary_currency=s_cur,
            salary_period=s_period,
            employment_type_raw=raw_job.get("employmentType"),
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("publishedAt"),
        )
