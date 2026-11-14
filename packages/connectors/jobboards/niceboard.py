from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record


class NiceboardConnector(BaseConnector):
    connector_key = "niceboard"
    platform_name = "Niceboard"
    category = "JOB_BOARD"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 40

    def _origin(self, url: str) -> str:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        origin = self._origin(source_url)
        if ".niceboard.co" in origin.lower():
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                canonical_source_url=origin,
                evidence="Matched *.niceboard.co domain",
            )
        try:
            resp = await self.http.get(origin, headers={"Accept": "text/html"}, rate_limit_rpm=30)
            txt = resp.text
            if "var jobboard_id =" in txt and "initial_filters" in txt:
                return DiscoveryProbeResult(
                    detected=True,
                    platform_key=self.connector_key,
                    confidence=0.97,
                    canonical_source_url=origin,
                    evidence="Detected Niceboard initial_filters and jobboard_id runtime signature",
                )
            if "Powered by Niceboard" in txt or "niceboard.co" in txt:
                return DiscoveryProbeResult(
                    detected=True,
                    platform_key=self.connector_key,
                    confidence=0.94,
                    canonical_source_url=origin,
                    evidence="Detected 'Powered by Niceboard' attribution in HTML",
                )
        except Exception:
            pass
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        origin = self._origin(source.source_url)
        page = int(cursor) if cursor and cursor.isdigit() else 1
        api_url = f"{origin}/api/jobs"

        params = {
            "company": "all",
            "jobtype": "[]",
            "category": "[]",
            "secondary_category": "[]",
            "tags": "[]",
            "city": "[]",
            "state": "[]",
            "country": "[]",
            "remote_ok": "false",
            "remote_only": "false",
            "salary_timeframe": "",
            "salary_min": "",
            "salary_max": "",
            "custom_fields": "{}",
            "sortby": "default",
            "keyword": "",
            "location": "",
            "page": str(page),
        }

        resp = await self.http.get(
            api_url,
            params=params,
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        data = resp.json()
        raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
        total_count = int(data.get("count", len(raw_jobs))) if isinstance(data, dict) else len(raw_jobs)

        max_jobs = source.extra_config.get("max_jobs")
        has_more = len(raw_jobs) > 0 and (page * len(raw_jobs)) < total_count
        next_cursor = str(page + 1) if has_more else None
        is_complete = True

        if isinstance(max_jobs, int) and max_jobs > 0:
            if page == 1 and len(raw_jobs) > max_jobs:
                raw_jobs = raw_jobs[:max_jobs]
                next_cursor = None
                is_complete = False
            elif next_cursor and (page * len(raw_jobs)) >= max_jobs:
                next_cursor = None
                is_complete = False

        payloads = []
        for item in raw_jobs:
            uid = str(item.get("uid") or item.get("id") or "")
            if not uid:
                continue
            slug = item.get("slug") or uid
            job_url = f"{origin}/jobs/{uid}-{slug}" if not str(slug).startswith(uid) else f"{origin}/jobs/{slug}"
            if item.get("permalink"):
                job_url = f"{origin}/{str(item['permalink']).lstrip('/')}"
            payloads.append(RawJobPayload(external_job_id=uid, raw_data=item, source_url=job_url))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=next_cursor,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={
                "api_url": api_url,
                "page": page,
                "total_count": total_count,
                "latency_ms": resp.latency_ms,
            },
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        origin = self._origin(source.source_url)
        uid = str(raw_job.get("uid") or raw_job.get("id"))
        slug = raw_job.get("slug") or uid
        job_url = f"{origin}/jobs/{uid}-{slug}"
        apply_url = raw_job.get("apply_url") or job_url

        comp_obj = raw_job.get("company") or {}
        company_name = (
            comp_obj.get("name")
            if isinstance(comp_obj, dict) and comp_obj.get("name")
            else (raw_job.get("company_name") or source.company_name)
        )

        jtype = raw_job.get("jobtype") or {}
        emp_raw = jtype.get("name") if isinstance(jtype, dict) else (str(jtype) if jtype else None)

        cat = raw_job.get("category") or {}
        dept = cat.get("name") if isinstance(cat, dict) else None

        wp_raw = "Remote" if raw_job.get("remote") is True or raw_job.get("is_remote") is True else None

        return normalize_job_record(
            external_job_id=uid,
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=company_name,
            description_html_or_text=raw_job.get("description_html") or raw_job.get("description") or "",
            source_job_url=job_url,
            application_url=str(apply_url),
            department=dept,
            location_raw=raw_job.get("location_name") or raw_job.get("location"),
            city=raw_job.get("city"),
            region=raw_job.get("state"),
            country=raw_job.get("country"),
            salary_min=raw_job.get("salary_min"),
            salary_max=raw_job.get("salary_max"),
            salary_currency=raw_job.get("salary_currency") or "USD",
            salary_period=raw_job.get("salary_timeframe"),
            employment_type_raw=emp_raw,
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("published_at") or raw_job.get("created_at"),
        )
