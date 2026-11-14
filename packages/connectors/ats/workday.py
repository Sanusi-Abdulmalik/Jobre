from __future__ import annotations

import asyncio
import re
from typing import Any

from packages.common.http_client import HttpFetchError
from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

WORKDAY_URL_RE = re.compile(
    r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:([a-z]{2}-[A-Z]{2})/)?([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


class WorkdayConnector(BaseConnector):
    connector_key = "workday"
    platform_name = "Workday"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 30

    def _parse_workday_url(self, url: str) -> tuple[str, str, str] | None:
        m = WORKDAY_URL_RE.search(url)
        if not m:
            return None
        tenant, cluster, _locale, site = m.group(1), m.group(2), m.group(3), m.group(4)
        if site.lower() == "wday":
            cxs_m = re.search(r"/wday/cxs/([^/]+)/([^/]+)", url)
            if cxs_m:
                return tenant, cluster, cxs_m.group(2)
            return None
        return tenant, cluster, site

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        parsed = self._parse_workday_url(source_url)
        if parsed:
            tenant, cluster, site = parsed
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.99,
                board_token=f"{tenant}|{cluster}|{site}",
                canonical_source_url=f"https://{tenant}.{cluster}.myworkdayjobs.com/{site}",
                company_name_hint=tenant.replace("-", " ").title(),
                evidence=f"Matched Workday CXS career site '{tenant}.{cluster}/{site}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_job_detail(
        self,
        base_cxs: str,
        item: dict[str, Any],
        rpm: int,
    ) -> dict[str, Any]:
        ext_path = item.get("externalPath")
        if not ext_path:
            return item
        try:
            detail_url = f"{base_cxs}{ext_path}"
            resp = await self.http.get(
                detail_url,
                headers={"Accept": "application/json"},
                rate_limit_rpm=rpm,
            )
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("jobPostingInfo"), dict):
                return {**item, "jobPostingInfo": data["jobPostingInfo"]}
        except Exception:
            pass
        return item

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        if source.board_token and source.board_token.count("|") == 2:
            tenant, cluster, site = source.board_token.split("|")
        else:
            parsed = self._parse_workday_url(source.source_url)
            if not parsed:
                raise ValueError(f"Cannot parse Workday tenant/cluster/site from '{source.source_url}'")
            tenant, cluster, site = parsed

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        max_jobs = source.extra_config.get("max_jobs", 20)
        limit = min(20, max_jobs if isinstance(max_jobs, int) and max_jobs > 0 else 20)

        origin = f"https://{tenant}.{cluster}.myworkdayjobs.com"
        base_cxs = f"{origin}/wday/cxs/{tenant}/{site}"
        jobs_url = f"{base_cxs}/jobs"

        resp = await self.http.post(
            jobs_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": origin,
                "Referer": f"{origin}/{site}",
            },
            json_body={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
            rate_limit_rpm=source.rate_limit_rpm,
        )

        ctype = resp.headers.get("content-type", "")
        if "application/json" not in ctype:
            raise HttpFetchError(
                f"Workday endpoint returned unexpected content-type '{ctype}' (possible maintenance or invalid site)",
                status_code=503,
                url=jobs_url,
                retryable=True,
                reason="non_json_workday_response",
            )

        data = resp.json()
        postings = data.get("jobPostings", []) if isinstance(data, dict) else []
        total = int(data.get("total", len(postings))) if isinstance(data, dict) else len(postings)

        sem = asyncio.Semaphore(4)

        async def _enrich(it: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                return await self._fetch_job_detail(base_cxs, it, max(source.rate_limit_rpm, 40))

        enriched = await asyncio.gather(*[_enrich(it) for it in postings])

        next_offset = offset + len(enriched)
        has_more = next_offset < total and len(enriched) > 0
        next_cursor = str(next_offset) if has_more else None
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and next_offset >= max_jobs and has_more:
            next_cursor = None
            is_complete = False

        payloads = []
        for item in enriched:
            info = item.get("jobPostingInfo") or {}
            ext_path = str(item.get("externalPath") or "")
            req_id = str(
                info.get("jobReqId")
                or (item.get("bulletFields") or [""])[0]
                or ext_path.rsplit("_", 1)[-1]
                or ext_path
            ).strip()
            if not req_id:
                continue
            public_url = info.get("externalUrl") or f"{origin}/en-US/{site}{ext_path}"
            payloads.append(RawJobPayload(external_job_id=req_id, raw_data=item, source_url=public_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=next_cursor,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={
                "api_url": jobs_url,
                "offset": offset,
                "total": total,
                "latency_ms": resp.latency_ms,
            },
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        info = raw_job.get("jobPostingInfo") or {}
        ext_path = str(raw_job.get("externalPath") or "")
        req_id = str(
            info.get("jobReqId")
            or (raw_job.get("bulletFields") or [""])[0]
            or ext_path.rsplit("_", 1)[-1]
            or ext_path
        )
        title = str(info.get("title") or raw_job.get("title") or "Untitled Role")
        desc_html = info.get("jobDescription") or title
        loc_raw = info.get("location") or raw_job.get("locationsText")
        country_obj = info.get("country") or {}
        country_name = country_obj.get("descriptor") if isinstance(country_obj, dict) else None
        country_code = country_obj.get("alpha2Code") if isinstance(country_obj, dict) else None

        public_url = str(info.get("externalUrl") or source.source_url)

        return normalize_job_record(
            external_job_id=req_id,
            title=title,
            company_name=source.company_name,
            description_html_or_text=desc_html,
            source_job_url=public_url,
            application_url=public_url,
            location_raw=loc_raw,
            country=country_name,
            country_code=country_code,
            employment_type_raw=info.get("timeType") or raw_job.get("timeType"),
            workplace_type_raw=info.get("remoteType") or raw_job.get("remoteType"),
            original_posted_at=info.get("startDate"),
        )
