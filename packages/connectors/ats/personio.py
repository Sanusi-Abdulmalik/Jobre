from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

PERSONIO_RE = re.compile(r"([a-z0-9-]+)\.jobs\.personio\.(de|com)", re.I)


class PersonioConnector(BaseConnector):
    connector_key = "personio"
    platform_name = "Personio"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 45

    def _extract_host_parts(self, url: str) -> tuple[str | None, str]:
        m = PERSONIO_RE.search(url)
        if m:
            return m.group(1).lower(), m.group(2).lower()
        return None, "de"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug, tld = self._extract_host_parts(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=f"{slug}.{tld}",
                canonical_source_url=f"https://{slug}.jobs.personio.{tld}",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Personio Career Page '{slug}.jobs.personio.{tld}'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        token = source.board_token
        if token and "." in token:
            slug, tld = token.split(".", 1)
        else:
            slug_parsed, tld = self._extract_host_parts(source.source_url)
            slug = token or slug_parsed
        if not slug:
            raise ValueError(f"Cannot determine Personio career host from '{source.source_url}'")

        xml_url = f"https://{slug}.jobs.personio.{tld}/xml?language=en"
        resp = await self.http.get(
            xml_url,
            headers={"Accept": "application/xml, text/xml"},
            rate_limit_rpm=source.rate_limit_rpm,
        )

        root = ET.fromstring(resp.text)
        positions = root.findall(".//position")
        max_jobs = source.extra_config.get("max_jobs")
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(positions) > max_jobs:
            positions = positions[:max_jobs]
            is_complete = False

        payloads: list[RawJobPayload] = []
        for pos in positions:
            pos_id = (pos.findtext("id") or "").strip()
            if not pos_id:
                continue
            descriptions = []
            for jd in pos.findall(".//jobDescription"):
                hdr = (jd.findtext("name") or "").strip()
                val = (jd.findtext("value") or "").strip()
                if val:
                    descriptions.append(f"<h3>{hdr}</h3>{val}" if hdr else val)

            raw_dict = {
                "id": pos_id,
                "name": (pos.findtext("name") or "").strip(),
                "subcompany": (pos.findtext("subcompany") or "").strip(),
                "office": (pos.findtext("office") or "").strip(),
                "department": (pos.findtext("department") or "").strip(),
                "recruitingCategory": (pos.findtext("recruitingCategory") or "").strip(),
                "employmentType": (pos.findtext("employmentType") or "").strip(),
                "seniority": (pos.findtext("seniority") or "").strip(),
                "schedule": (pos.findtext("schedule") or "").strip(),
                "createdAt": (pos.findtext("createdAt") or "").strip(),
                "description_html": "\n".join(descriptions),
                "job_url": f"https://{slug}.jobs.personio.{tld}/job/{pos_id}?language=en",
            }
            payloads.append(
                RawJobPayload(
                    external_job_id=pos_id,
                    raw_data=raw_dict,
                    source_url=raw_dict["job_url"],
                )
            )

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=None,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"xml_url": xml_url, "latency_ms": resp.latency_ms},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        ext_id = str(raw_job.get("id"))
        job_url = str(raw_job.get("job_url") or source.source_url)
        emp_raw = f"{raw_job.get('employmentType') or ''} {raw_job.get('schedule') or ''}".strip() or None
        company_name = raw_job.get("subcompany") or source.company_name

        return normalize_job_record(
            external_job_id=ext_id,
            title=str(raw_job.get("name") or "Untitled Role"),
            company_name=company_name,
            description_html_or_text=raw_job.get("description_html") or raw_job.get("name") or "",
            source_job_url=job_url,
            application_url=f"{job_url}#apply",
            department=raw_job.get("department") or raw_job.get("recruitingCategory"),
            location_raw=raw_job.get("office") or None,
            employment_type_raw=emp_raw,
            original_posted_at=raw_job.get("createdAt"),
        )
