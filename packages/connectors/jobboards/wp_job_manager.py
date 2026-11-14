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


class WPJobManagerConnector(BaseConnector):
    connector_key = "wp_job_manager"
    platform_name = "WP Job Manager"
    category = "JOB_BOARD"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 40

    def _origin(self, url: str) -> str:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        origin = self._origin(source_url)
        if "/wp-json/wp/v2/job-listings" in source_url.lower():
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                canonical_source_url=f"{origin}/wp-json/wp/v2/job-listings",
                evidence="Matched WordPress REST API /wp-json/wp/v2/job-listings endpoint",
            )
        try:
            probe_url = f"{origin}/wp-json/wp/v2/job-listings?per_page=1"
            resp = await self.http.get(probe_url, headers={"Accept": "application/json"}, rate_limit_rpm=30)
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                return DiscoveryProbeResult(
                    detected=True,
                    platform_key=self.connector_key,
                    confidence=0.97,
                    canonical_source_url=f"{origin}/wp-json/wp/v2/job-listings",
                    evidence="Verified live /wp-json/wp/v2/job-listings WP Job Manager route",
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
        per_page = min(int(source.extra_config.get("page_size", 50)), 100)

        api_url = f"{origin}/wp-json/wp/v2/job-listings"
        resp = await self.http.get(
            api_url,
            params={"page": page, "per_page": per_page},
            headers={"Accept": "application/json"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        items = resp.json()
        if not isinstance(items, list):
            items = []

        total_pages = int(resp.headers.get("x-wp-totalpages", "1") or "1")
        has_more = page < total_pages and len(items) > 0
        next_cursor = str(page + 1) if has_more else None

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and (page * per_page) >= max_jobs and has_more:
            next_cursor = None
            is_complete = False

        payloads = []
        for item in items:
            ext_id = str(item.get("id") or "")
            if not ext_id:
                continue
            link = str(item.get("link") or f"{origin}/?p={ext_id}")
            payloads.append(RawJobPayload(external_job_id=ext_id, raw_data=item, source_url=link))

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
        ext_id = str(raw_job.get("id"))
        title_obj = raw_job.get("title") or {}
        title = title_obj.get("rendered") if isinstance(title_obj, dict) else str(title_obj or "Untitled Role")
        content_obj = raw_job.get("content") or {}
        desc_html = content_obj.get("rendered") if isinstance(content_obj, dict) else str(content_obj or "")

        meta = raw_job.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}

        company = meta.get("_company_name") or source.company_name
        location = meta.get("_job_location") or None
        app_target = meta.get("_application") or ""
        link = str(raw_job.get("link") or source.source_url)
        apply_url = app_target if isinstance(app_target, str) and app_target.startswith("http") else link
        wp_raw = "Remote" if str(meta.get("_remote_position")) in ("1", "true", "True") else None

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(title),
            company_name=str(company),
            description_html_or_text=str(desc_html),
            source_job_url=link,
            application_url=apply_url,
            location_raw=location,
            salary_raw=meta.get("_job_salary"),
            salary_currency=meta.get("_job_salary_currency"),
            salary_period=meta.get("_job_salary_unit"),
            workplace_type_raw=wp_raw,
            original_posted_at=raw_job.get("date_gmt") or raw_job.get("date"),
        )
