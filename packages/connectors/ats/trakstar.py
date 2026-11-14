from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urljoin

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

TRAKSTAR_RE = re.compile(r"([a-z0-9-]+)\.hire\.trakstar\.com", re.I)
TRAKSTAR_JOB_RE = re.compile(r"/jobs/(fk[a-z0-9]+)/?", re.I)


class TrakstarConnector(BaseConnector):
    connector_key = "trakstar"
    platform_name = "Trakstar"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 30

    def _extract_slug(self, url: str) -> str | None:
        m = TRAKSTAR_RE.search(url)
        if m and m.group(1).lower() not in ("www", "app"):
            return m.group(1).lower()
        return None

    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        slug = self._extract_slug(source_url)
        if slug:
            return DiscoveryProbeResult(
                detected=True,
                platform_key=self.connector_key,
                confidence=0.98,
                board_token=slug,
                canonical_source_url=f"https://{slug}.hire.trakstar.com/",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched Trakstar Hire subdomain '{slug}.hire.trakstar.com'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_detail(self, job_url: str, code: str, title_hint: str, rpm: int) -> dict[str, Any]:
        raw: dict[str, Any] = {"id": code, "url": job_url, "title": title_hint}
        try:
            resp = await self.http.get(job_url, headers={"Accept": "text/html"}, rate_limit_rpm=rpm)
            ld = extract_jsonld_job_posting(resp.text)
            if ld:
                raw["json_ld"] = ld
                return raw
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_el = soup.select_one(".js-job-description, .jobdesciption, .rb-job-description")
            if desc_el:
                raw["description_html"] = str(desc_el)
        except Exception:
            pass
        return raw

    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        slug = source.board_token or self._extract_slug(source.source_url)
        if not slug:
            raise ValueError(f"Cannot determine Trakstar Hire subdomain from '{source.source_url}'")

        board_url = f"https://{slug}.hire.trakstar.com/"
        resp = await self.http.get(board_url, headers={"Accept": "text/html"}, rate_limit_rpm=source.rate_limit_rpm)
        soup = BeautifulSoup(resp.text, "html.parser")

        found: dict[str, tuple[str, str]] = {}
        for a in soup.find_all("a", href=True):
            m = TRAKSTAR_JOB_RE.search(a["href"])
            if not m:
                continue
            code = m.group(1).lower()
            full_url = urljoin(board_url, f"/jobs/{code}/")
            title_txt = a.get_text(" ", strip=True) or code
            if code not in found or len(title_txt) > len(found[code][1]):
                found[code] = (full_url, title_txt)

        entries = list(found.items())
        max_jobs = source.extra_config.get("max_jobs", 20)
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(entries) > max_jobs:
            entries = entries[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(4)

        async def _load(entry: tuple[str, tuple[str, str]]) -> RawJobPayload:
            code, (jurl, jtitle) = entry
            async with sem:
                data = await self._fetch_detail(jurl, code, jtitle, max(source.rate_limit_rpm, 35))
            return RawJobPayload(external_job_id=code, raw_data=data, source_url=jurl)

        payloads = list(await asyncio.gather(*[_load(e) for e in entries]))

        return FetchBatchResult(
            jobs=payloads,
            next_cursor=None,
            http_status=resp.status_code,
            is_complete=is_complete,
            request_metadata={"board_url": board_url, "latency_ms": resp.latency_ms, "slug": slug},
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
        org = ld.get("hiringOrganization") or {}
        company_name = org.get("name") if isinstance(org, dict) and org.get("name") else source.company_name

        emp_type = ld.get("employmentType")
        if isinstance(emp_type, list) and emp_type:
            emp_type = emp_type[0]

        return normalize_job_record(
            external_job_id=ext_id,
            title=title,
            company_name=company_name,
            description_html_or_text=desc,
            source_job_url=job_url,
            application_url=job_url,
            city=city,
            region=region,
            country=country,
            employment_type_raw=emp_type if isinstance(emp_type, str) else None,
            workplace_type_raw=wp_raw,
            original_posted_at=ld.get("datePosted"),
        )
