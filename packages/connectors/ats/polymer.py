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

POLYMER_RE = re.compile(
    r"(?:jobs\.polymer\.co|api\.polymer\.co/v1/hire/organizations)/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


class PolymerConnector(BaseConnector):
    connector_key = "polymer"
    platform_name = "Polymer"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        m = POLYMER_RE.search(url)
        return m.group(1).strip("/") if m else None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://jobs.polymer.co/{slug}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Polymer organization '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _enrich_detail(self, slug: str, item: dict[str, Any], rpm: int) -> dict[str, Any]:
        job_id = item.get("id") or item.get("job_id")
        if not job_id:
            return item
        try:
            url = f"https://jobs.polymer.co/{slug}/{job_id}"
            resp = await self.http.get(url, headers={"Accept": "text/html"}, rate_limit_rpm=rpm)
            ld = extract_jsonld_job_posting(resp.text)
            if ld:
                return {**item, "json_ld": ld}
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
            raise ValueError(f"Cannot determine Polymer organization slug from '{source.source_url}'")

        api_url = f"https://api.polymer.co/v1/hire/organizations/{slug}/jobs"
        resp = await self.http.get(api_url, headers={"Accept": "application/json"}, rate_limit_rpm=source.rate_limit_rpm)
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(items) > max_jobs:
            items = items[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(4)

        async def _enrich(it: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self._enrich_detail(slug, it, max(source.rate_limit_rpm, 45))

        enriched = await asyncio.gather(*[_enrich(it) for it in items[:20]]) + items[20:]

        payloads = []
        for item in enriched:
            ext_id = str(item.get("id") or item.get("job_id") or "")
            if not ext_id:
                continue
            job_url = f"https://jobs.polymer.co/{slug}/{ext_id}"
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
        slug = source.board_token or self._extract_slug(source.source_url) or ""
        ext_id = str(raw_job.get("id") or raw_job.get("job_id"))
        job_url = f"https://jobs.polymer.co/{slug}/{ext_id}"

        ld = raw_job.get("json_ld") or {}
        desc = ld.get("description") or raw_job.get("description") or raw_job.get("title") or ""

        base_sal = ld.get("baseSalary") or {}
        sal_val = base_sal.get("value") if isinstance(base_sal, dict) else {}
        s_min = sal_val.get("minValue") if isinstance(sal_val, dict) else None
        s_max = sal_val.get("maxValue") if isinstance(sal_val, dict) else None
        s_cur = base_sal.get("currency") if isinstance(base_sal, dict) else None
        s_unit = sal_val.get("unitText") if isinstance(sal_val, dict) else None

        city = raw_job.get("city")
        region = raw_job.get("state_region")
        country = raw_job.get("country")
        loc_raw = raw_job.get("display_location") or ", ".join([p for p in (city, region, country) if p]) or None

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=(ld.get("hiringOrganization") or {}).get("name") or source.company_name,
            description_html_or_text=desc,
            source_job_url=job_url,
            application_url=job_url,
            department=raw_job.get("category_name"),
            location_raw=loc_raw,
            city=city,
            region=region,
            country=country,
            salary_min=s_min,
            salary_max=s_max,
            salary_currency=s_cur,
            salary_period=s_unit,
            employment_type_raw=raw_job.get("kind_pretty") or ld.get("employmentType"),
            workplace_type_raw=raw_job.get("remoteness_pretty"),
            original_posted_at=raw_job.get("published_at") or ld.get("datePosted"),
        )
