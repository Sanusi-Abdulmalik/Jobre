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

SR_RE = re.compile(
    r"(?:(?:careers|jobs)\.smartrecruiters\.com|api\.smartrecruiters\.com/v1/companies)/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


class SmartRecruitersConnector(BaseConnector):
    connector_key = "smartrecruiters"
    platform_name = "SmartRecruiters"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 60

    def _extract_slug(self, url: str) -> str | None:
        m = SR_RE.search(url)
        return m.group(1).strip("/") if m else None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.97,
                board_token=slug,
                canonical_source_url=f"https://careers.smartrecruiters.com/{slug}",
                company_name_hint=slug,
                evidence=f"Matched SmartRecruiters company identifier '{slug}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _enrich_detail(self, slug: str, item: dict[str, Any], rpm: int) -> dict[str, Any]:
        job_id = item.get("id")
        if not job_id:
            return item
        try:
            detail_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{job_id}"
            resp = await self.http.get(detail_url, headers={"Accept": "application/json"}, rate_limit_rpm=rpm)
            detail = resp.json()
            if isinstance(detail, dict):
                merged = {**item, **detail}
                return merged
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
            raise ValueError(f"Cannot determine SmartRecruiters company identifier from '{source.source_url}'")

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        max_jobs = source.extra_config.get("max_jobs", 25)
        page_limit = min(int(source.extra_config.get("page_size", 25)), max_jobs if isinstance(max_jobs, int) and max_jobs > 0 else 50)

        api_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        resp = await self.http.get(
            api_url,
            params={"offset": offset, "limit": page_limit},
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        data = resp.json()
        raw_items = data.get("content", []) if isinstance(data, dict) else []
        total_found = int(data.get("totalFound", len(raw_items))) if isinstance(data, dict) else len(raw_items)

        # Fetch full HTML jobAd sections with bounded concurrency (max 4 at once)
        sem = asyncio.Semaphore(4)

        async def _fetch_one(it: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self._enrich_detail(slug, it, max(source.rate_limit_rpm, 60))

        enriched_items = await asyncio.gather(*[_fetch_one(it) for it in raw_items])

        next_offset = offset + len(enriched_items)
        has_more = next_offset < total_found and len(enriched_items) > 0
        next_cursor = str(next_offset) if has_more else None
        is_complete = True

        if isinstance(max_jobs, int) and max_jobs > 0 and next_offset >= max_jobs and has_more:
            next_cursor = None
            is_complete = False

        payloads = []
        for item in enriched_items:
            ext_id = str(item.get("id") or "")
            if not ext_id:
                continue
            posting_url = item.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{ext_id}"
            payloads.append(RawJobPayload(external_job_id=ext_id, raw_data=item, source_url=posting_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=next_cursor,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={
                "api_url": api_url,
                "offset": offset,
                "total_found": total_found,
                "latency_ms": resp.latency_ms,
            },
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        ext_id = str(raw_job.get("id"))
        slug = source.board_token or self._extract_slug(source.source_url) or ""
        loc = raw_job.get("location") or {}
        city = loc.get("city")
        region = loc.get("region")
        country_code = (loc.get("country") or "").upper() or None
        full_loc = loc.get("fullLocation") or ", ".join([p for p in (city, region, country_code) if p])

        sections = ((raw_job.get("jobAd") or {}).get("sections") or {})
        html_parts = []
        for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
            sec = sections.get(key)
            if isinstance(sec, dict) and sec.get("text"):
                title_hdr = f"<h3>{sec['title']}</h3>" if sec.get("title") else ""
                html_parts.append(f"{title_hdr}{sec['text']}")
        desc_html = "\n".join(html_parts) or str(raw_job.get("name") or "")

        emp_obj = raw_job.get("typeOfEmployment") or {}
        emp_raw = emp_obj.get("label") or emp_obj.get("id")
        wp_raw = "Remote" if loc.get("remote") is True else ("Hybrid" if loc.get("hybrid") is True else "On-site")

        comp = raw_job.get("compensation") or {}
        posting_url = raw_job.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{ext_id}"
        apply_url = raw_job.get("applyUrl") or posting_url
        company_obj = raw_job.get("company") or {}
        company_name = company_obj.get("name") or source.company_name

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("name") or "Untitled Role"),
            company_name=company_name,
            description_html_or_text=desc_html,
            source_job_url=posting_url,
            application_url=apply_url,
            department=(raw_job.get("department") or {}).get("label"),
            location_raw=full_loc or None,
            city=city,
            region=region,
            country_code=country_code,
            salary_min=comp.get("min"),
            salary_max=comp.get("max"),
            salary_currency=comp.get("currency"),
            employment_type_raw=emp_raw,
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("releasedDate"),
        )
