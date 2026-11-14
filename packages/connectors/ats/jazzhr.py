from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from packages.common.security import canonicalize_url
from packages.connectors.base import (
    BaseConnector,
    ConnectorSourceConfig,
    DiscoveryProbeResult,
    FetchBatchResult,
    RawJobPayload,
    extract_jsonld_job_posting,
)
from packages.normalization.engine import NormalizedJobInput, normalize_job_record

JAZZ_RE = re.compile(r"([a-z0-9-]+)\.applytojob\.com", re.I)
JAZZ_JOB_PATH_RE = re.compile(r"/apply/([a-zA-Z0-9]{6,16})(?:/([^/?#&]+))?")


class JazzHRConnector(BaseConnector):
    connector_key = "jazzhr"
    platform_name = "JazzHR"
    category = "ATS"
    extraction_version = "1.1.0"
    default_rate_limit_rpm = 30

    def _extract_slug(self, url: str) -> str | None:
        m = JAZZ_RE.search(url)
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
                canonical_source_url=f"https://{slug}.applytojob.com/apply",
                company_name_hint=slug.replace("-", " ").title(),
                evidence=f"Matched JazzHR board '{slug}.applytojob.com'",
            )
        return DiscoveryProbeResult(detected=False, platform_key=self.connector_key, confidence=0.0)

    async def _fetch_job_page(self, job_url: str, ext_id: str, fallback_title: str, rpm: int) -> dict[str, Any]:
        raw: dict[str, Any] = {"id": ext_id, "url": job_url, "title": fallback_title}
        try:
            resp = await self.http.get(job_url, headers={"Accept": "text/html"}, rate_limit_rpm=rpm)
            ld = extract_jsonld_job_posting(resp.text)
            if ld:
                raw["json_ld"] = ld
                return raw
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_el = soup.select_one("#job-description, .description, [itemprop='description']")
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
            raise ValueError(f"Cannot determine JazzHR subdomain from '{source.source_url}'")

        board_url = f"https://{slug}.applytojob.com/apply"
        resp = await self.http.get(board_url, headers={"Accept": "text/html"}, rate_limit_rpm=source.rate_limit_rpm)
        soup = BeautifulSoup(resp.text, "html.parser")

        discovered: dict[str, tuple[str, str]] = {}
        for a in soup.find_all("a", href=True):
            clean_href = canonicalize_url(urljoin(board_url, a["href"])) or ""
            m = JAZZ_JOB_PATH_RE.search(clean_href)
            if not m:
                continue
            job_code = m.group(1)
            if job_code.lower() in ("jobs", "apply"):
                continue
            title_txt = a.get_text(" ", strip=True) or (m.group(2) or job_code).replace("-", " ")
            discovered[job_code] = (clean_href, title_txt)

        entries = list(discovered.items())
        max_jobs = source.extra_config.get("max_jobs", 25)
        is_complete = True
        if isinstance(max_jobs, int) and max_jobs > 0 and len(entries) > max_jobs:
            entries = entries[:max_jobs]
            is_complete = False

        sem = asyncio.Semaphore(3)

        async def _load(code_and_info: tuple[str, tuple[str, str]]) -> RawJobPayload:
            code, (jurl, jtitle) = code_and_info
            async with sem:
                detail = await self._fetch_job_page(jurl, code, jtitle, max(source.rate_limit_rpm, 30))
            return RawJobPayload(external_job_id=code, raw_data=detail, source_url=jurl)

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
            employment_type_raw=ld.get("employmentType") if isinstance(ld.get("employmentType"), str) else None,
            workplace_type_raw=wp_raw,
            original_posted_at=ld.get("datePosted"),
        )
