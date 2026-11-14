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

TT_SUB_RE = re.compile(r"([a-z0-9-]+)\.teamtailor\.com", re.I)


class TeamtailorConnector(BaseConnector):
    connector_key = "teamtailor"
    platform_name = "Teamtailor"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 45

    def _base_origin(self, url: str) -> str:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        m = TT_SUB_RE.search(source_url)
        if m and m.group(1).lower() not in ("www", "docs", "api", "app"):
            sub = m.group(1).lower()
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.97,
                board_token=sub,
                canonical_source_url=f"https://{sub}.teamtailor.com/jobs",
                company_name_hint=sub.replace("-", " ").title(),
                evidence=f"Matched Teamtailor subdomain '{sub}.teamtailor.com'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        origin = self._base_origin(source.source_url)
        rss_url = source.source_url if source.source_url.endswith(".rss") else f"{origin}/jobs.rss"

        resp = await self.http.get(
            rss_url,
            headers={"Accept": "application/rss+xml, application/xml, text/xml"},
            rate_limit_rpm=source.rate_limit_rpm,
        )

        ns = {
            "tt": "https://teamtailor.com/locations",
            "dc": "http://purl.org/dc/elements/1.1/",
        }
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
            ext_id = guid.rstrip("/").rsplit("/", 1)[-1] or guid

            locs = []
            for loc_node in item.findall("tt:location", ns):
                city = (loc_node.findtext("tt:city", default="", namespaces=ns) or "").strip()
                country = (loc_node.findtext("tt:country", default="", namespaces=ns) or "").strip()
                name = (loc_node.findtext("tt:name", default="", namespaces=ns) or "").strip()
                joined = ", ".join([p for p in (city, country) if p]) or name
                if joined:
                    locs.append({"city": city or None, "country": country or None, "display": joined})

            remote_status = (item.findtext("remoteStatus") or "").strip()
            dept = (item.findtext("department") or "").strip()
            raw_dict = {
                "id": ext_id,
                "guid": guid,
                "title": (item.findtext("title") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "link": link,
                "pubDate": (item.findtext("pubDate") or "").strip(),
                "remoteStatus": remote_status or None,
                "department": dept or None,
                "locations": locs,
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
        locs = raw_job.get("locations") or []
        first_loc = locs[0] if locs and isinstance(locs[0], dict) else {}
        loc_raw = "; ".join([l.get("display", "") for l in locs if isinstance(l, dict) and l.get("display")]) or None
        link = str(raw_job.get("link") or source.source_url)

        return normalize_job_record(
            external_job_id=str(raw_job.get("id")),
            title=str(raw_job.get("title") or "Untitled Role"),
            company_name=source.company_name,
            description_html_or_text=raw_job.get("description") or "",
            source_job_url=link,
            application_url=link,
            department=raw_job.get("department"),
            location_raw=loc_raw,
            city=first_loc.get("city"),
            country=first_loc.get("country"),
            workplace_type_raw=raw_job.get("remoteStatus"),
            original_posted_at=raw_job.get("pubDate"),
        )
