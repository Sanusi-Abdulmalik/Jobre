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

SJB_JOB_PATH_RE = re.compile(r"/job/(\d+)/([a-zA-Z0-9_-]+)/?")


class SmartJobBoardConnector(BaseConnector):
    connector_key = "smartjobboard"
    platform_name = "SmartJobBoard"
    category = "JOB_BOARD"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 30

    def _origin(self, url: str) -> str:
        parsed = urlparse(url.strip())
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        origin = self._origin(source_url)
        if ".mysmartjobboard." in origin.lower():
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                canonical_source_url=origin,
                evidence="Matched *.mysmartjobboard.* domain",
            )
        try:
            resp = await self.http.get(origin, headers={"Accept": "text/html"}, rate_limit_rpm=25)
            if "powered by smartjobboard" in resp.text.lower():
                return DiscoveryProbeResult(
                    detected=True,
                    platform_key=self.connector_key,
                    confidence=0.96,
                    canonical_source_url=origin,
                    evidence="Detected 'Powered by SmartJobBoard' attribution",
                )
        except Exception:
            pass
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_job_detail(self, job_url: str, job_id: str, fallback_title: str, rpm: int) -> dict[str, Any]:
        raw: dict[str, Any] = {"id": job_id, "url": job_url, "title": fallback_title}
        try:
            resp = await self.http.get(job_url, headers={"Accept": "text/html"}, rate_limit_rpm=rpm)
            ld = extract_jsonld_job_posting(resp.text)
            if ld:
                raw["json_ld"] = ld
            soup = BeautifulSoup(resp.text, "html.parser")
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                raw["title"] = h1.get_text(" ", strip=True)
            desc_el = soup.select_one(".job-details__description, .details-body, .listing-description, [itemprop='description']")
            if desc_el:
                raw["description_html"] = str(desc_el)
            comp_el = soup.select_one("a[href*='/company/'], .company-title, [itemprop='hiringOrganization']")
            if comp_el and comp_el.get_text(strip=True):
                raw["company_hint"] = comp_el.get_text(" ", strip=True)
            loc_el = soup.select_one(".location, [itemprop='jobLocation']")
            if loc_el and loc_el.get_text(strip=True):
                raw["location_hint"] = loc_el.get_text(" ", strip=True)
        except Exception:
            pass
        return raw

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        origin = self._origin(source.source_url)
        page = int(cursor) if cursor and cursor.isdigit() else 1
        list_url = f"{origin}/jobs/?page={page}" if page > 1 else f"{origin}/"

        resp = await self.http.get(list_url, headers={"Accept": "text/html"}, rate_limit_rpm=source.rate_limit_rpm)
        soup = BeautifulSoup(resp.text, "html.parser")

        found: dict[str, tuple[str, str]] = {}
        for a in soup.find_all("a", href=True):
            m = SJB_JOB_PATH_RE.search(a["href"])
            if not m:
                continue
            jid, slug = m.group(1), m.group(2)
            full_url = urljoin(origin, f"/job/{jid}/{slug}/")
            title_txt = a.get_text(" ", strip=True) or slug.replace("-", " ").title()
            if jid not in found or len(title_txt) > len(found[jid][1]):
                found[jid] = (full_url, title_txt)

        # If root page had few links, also check /jobs/
        if page == 1 and len(found) == 0:
            resp2 = await self.http.get(f"{origin}/jobs/", headers={"Accept": "text/html"}, rate_limit_rpm=source.rate_limit_rpm)
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            for a in soup2.find_all("a", href=True):
                m = SJB_JOB_PATH_RE.search(a["href"])
                if m:
                    jid, slug = m.group(1), m.group(2)
                    found[jid] = (urljoin(origin, f"/job/{jid}/{slug}/"), a.get_text(" ", strip=True) or slug)

        entries = list(found.items())
        max_jobs = source.extra_config.get("max_jobs", 20)
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(entries) > max_jobs:
            entries = entries[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(4)

        async def _load(entry: tuple[str, tuple[str, str]]) -> RawJobPayload:
            jid, (jurl, jtitle) = entry
            async with sem:
                detail = await self._fetch_job_detail(jurl, jid, jtitle, max(source.rate_limit_rpm, 35))
            return RawJobPayload(external_job_id=jid, raw_data=detail, source_url=jurl)

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
        company = (org.get("name") if isinstance(org, dict) else None) or raw_job.get("company_hint") or source.company_name

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
            location_raw=raw_job.get("location_hint"),
            city=city,
            region=region,
            country=country,
            employment_type_raw=emp_raw if isinstance(emp_raw, str) else None,
            workplace_type_raw=wp_raw,
            original_posted_at=ld.get("datePosted"),
        )
