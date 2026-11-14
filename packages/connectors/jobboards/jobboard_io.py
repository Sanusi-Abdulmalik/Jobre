from __future__ import annotations

import re
import xml.etree.ElementTree as ET
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


class JobBoardIoConnector(BaseConnector):
    connector_key = "jobboard_io"
    platform_name = "JobBoard.io"
    category = "JOB_BOARD"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 40

    def _origin(self, url: str) -> str:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        origin = self._origin(source_url)
        if ".jobboard.io" in origin.lower():
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                canonical_source_url=f"{origin}/jobs.rss",
                evidence="Matched *.jobboard.io domain",
            )
        try:
            resp = await self.http.get(origin, headers={"Accept": "text/html"}, rate_limit_rpm=30)
            if "jobboard.io" in resp.text.lower():
                return DiscoveryProbeResult(
                    detected=True,
                    platform_key=self.connector_key,
                    confidence=0.95,
                    canonical_source_url=f"{origin}/jobs.rss",
                    evidence="Detected JobBoard.io platform signature in HTML",
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
        rss_url = source.source_url if source.source_url.endswith(".rss") else f"{origin}/jobs.rss"

        resp = await self.http.get(
            rss_url,
            headers={"Accept": "application/rss+xml, application/xml, text/xml"},
            rate_limit_rpm=source.rate_limit_rpm,
        )
        root = ET.fromstring(resp.text)
        items = root.findall(".//item")

        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(items) > max_jobs:
            items = items[:max_jobs]
            is_complete = False

        payloads = []
        for item in items:
            guid = (item.findtext("guid") or item.findtext("link") or "").strip()
            link = (item.findtext("link") or guid).strip()
            if not link:
                continue
            m_id = re.search(r"/jobs/(\d+)", link)
            ext_id = m_id.group(1) if m_id else (guid.rstrip("/").rsplit("/", 1)[-1] or guid)

            author_company = (
                item.findtext("{http://purl.org/dc/elements/1.1/}creator")
                or item.findtext("author")
                or item.findtext("company")
                or ""
            ).strip()
            location = (item.findtext("location") or "").strip()
            raw_dict = {
                "id": ext_id,
                "guid": guid,
                "title": (item.findtext("title") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "link": link,
                "pubDate": (item.findtext("pubDate") or "").strip(),
                "company": author_company or None,
                "location": location or None,
            }
            payloads.append(RawJobPayload(external_job_id=ext_id, raw_data=raw_dict, source_url=link))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=None,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"rss_url": rss_url, "latency_ms": resp.latency_ms},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        raw_title = str(raw_job.get("title") or "Untitled Role")
        company = raw_job.get("company")
        location = raw_job.get("location")

        # JobBoard.io RSS titles often follow "Role Title at Company Name" or "Role Title - Company"
        if not company and " at " in raw_title:
            parts = raw_title.rsplit(" at ", 1)
            if len(parts[1]) < 70:
                raw_title, company = parts[0].strip(), parts[1].strip()

        link = str(raw_job.get("link") or source.source_url)
        return normalize_job_record(
            external_job_id=str(raw_job.get("id")),
            title=raw_title,
            company_name=company or source.company_name,
            description_html_or_text=raw_job.get("description") or raw_title,
            source_job_url=link,
            application_url=link,
            location_raw=location,
            original_posted_at=raw_job.get("pubDate"),
        )
