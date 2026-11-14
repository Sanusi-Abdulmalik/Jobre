from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
    extract_jsonld_job_posting,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

JOBBOARDLY_JOB_RE = re.compile(r"^/jobs/([a-z0-9-]+-([a-f0-9]{6,12}))/?$", re.I)


class JobboardlyConnector(BaseConnector):
    connector_key = "jobboardly"
    platform_name = "Jobboardly"
    category = "JOB_BOARD"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 30

    def _origin(self, url: str) -> str:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        origin = self._origin(source_url)
        if ".jobboardly.com" in origin.lower():
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                canonical_source_url=f"{origin}/jobs/",
                evidence="Matched *.jobboardly.com domain",
            )
        try:
            resp = await self.http.get(f"{origin}/jobs/", headers={"Accept": "text/html"}, rate_limit_rpm=25)
            soup = BeautifulSoup(resp.text, "html.parser")
            matching_links = [
                a["href"] for a in soup.find_all("a", href=True) if JOBBOARDLY_JOB_RE.match(urlparse(a["href"]).path)
            ]
            if "jobboardly" in resp.text.lower() or len(matching_links) >= 2:
                return DiscoveryProbeResult(
                    detected=True,
                    platform_key=self.connector_key,
                    confidence=0.93,
                    canonical_source_url=f"{origin}/jobs/",
                    evidence="Matched Jobboardly /jobs/{slug}-{hex} listing pattern",
                )
        except Exception:
            pass
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_detail(self, job_url: str, ext_id: str, title_hint: str, rpm: int) -> dict[str, Any]:
        raw: dict[str, Any] = {"id": ext_id, "url": job_url, "title": title_hint}
        try:
            resp = await self.http.get(job_url, headers={"Accept": "text/html"}, rate_limit_rpm=rpm)
            ld = extract_jsonld_job_posting(resp.text)
            if ld:
                raw["json_ld"] = ld
            soup = BeautifulSoup(resp.text, "html.parser")
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                raw["title"] = h1.get_text(" ", strip=True)
            article = soup.find("article") or soup.find("main")
            if article:
                raw["description_html"] = str(article)[:15000]
        except Exception:
            pass
        return raw

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        origin = self._origin(source.source_url)
        list_url = f"{origin}/jobs/"
        resp = await self.http.get(list_url, headers={"Accept": "text/html"}, rate_limit_rpm=source.rate_limit_rpm)
        soup = BeautifulSoup(resp.text, "html.parser")

        found: dict[str, tuple[str, str]] = {}
        for a in soup.find_all("a", href=True):
            parsed_href = urlparse(a["href"])
            m = JOBBOARDLY_JOB_RE.match(parsed_href.path)
            if not m:
                continue
            slug_full, hex_id = m.group(1), m.group(2)
            full_url = urljoin(origin, f"/jobs/{slug_full}")
            txt = a.get_text(" ", strip=True) or slug_full.replace("-", " ").title()
            if hex_id not in found or len(txt) > len(found[hex_id][1]):
                found[hex_id] = (full_url, txt)

        entries = list(found.items())
        max_jobs = source.extra_config.get("max_jobs", 15)
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(entries) > max_jobs:
            entries = entries[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(4)

        async def _load(entry: tuple[str, tuple[str, str]]) -> RawJobPayload:
            hid, (jurl, jtitle) = entry
            async with sem:
                detail = await self._fetch_detail(jurl, hid, jtitle, max(source.rate_limit_rpm, 35))
            return RawJobPayload(external_job_id=hid, raw_data=detail, source_url=jurl)

        payloads = list(await asyncio.gather(*[_load(e) for e in entries]))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=None,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"list_url": list_url, "latency_ms": resp.latency_ms},
        )

    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        ld = raw_job.get("json_ld") or {}
        ext_id = str(raw_job.get("id"))
        job_url = str(raw_job.get("url") or source.source_url)
        title = str(ld.get("title") or raw_job.get("title") or "Untitled Role")
        desc = ld.get("description") or raw_job.get("description_html") or title

        org = ld.get("hiringOrganization") or {}
        company = (org.get("name") if isinstance(org, dict) else None) or source.company_name

        loc_node = ld.get("jobLocation")
        if isinstance(loc_node, list) and loc_node:
            loc_node = loc_node[0]
        addr = loc_node.get("address") if isinstance(loc_node, dict) else {}
        if not isinstance(addr, dict):
            addr = {}

        city = addr.get("addressLocality")
        region = addr.get("addressRegion")
        country = addr.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")

        wp_raw = "Remote" if ld.get("jobLocationType") == "TELECOMMUTE" else None
        emp_raw = ld.get("employmentType")
        if isinstance(emp_raw, list) and emp_raw:
            emp_raw = emp_raw[0]

        return normalize_job_record(
            external_job_id=ext_id,
            title=title,
            company_name=company,
            description_html_or_text=desc,
            source_job_url=job_url,
            application_url=job_url,
            city=city,
            region=region,
            country=country,
            employment_type_raw=emp_raw if isinstance(emp_raw, str) else None,
            workplace_type_raw=wp_raw,
            original_posted_at=ld.get("datePosted"),
        )
