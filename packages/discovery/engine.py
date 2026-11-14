from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from packages.common.http_client import JobreHttpClient
from packages.common.security import extract_canonical_domain, validate_public_url
from packages.connectors.catalog import PLATFORM_CATALOG
from packages.connectors.registry import ConnectorRegistry, get_connector_registry


@dataclass
class SourceDiscoveryResult:
    input_url: str
    canonical_source_url: str
    canonical_domain: str
    detected: bool
    platform_key: str | None
    platform_name: str | None
    platform_category: str | None
    connector_implemented: bool
    board_token: str | None
    company_name: str
    source_type: str
    discovery_method: str
    confidence: float
    evidence: str


CAREER_LINK_HINTS = ("careers", "jobs", "open-positions", "join-us", "work-with-us", "vacancies")


class SourceDiscoveryEngine:
    """Identifies ATS and Job-Board technologies behind company websites, career URLs, and job boards."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry | None = None,
        http_client: JobreHttpClient | None = None,
        allow_private_urls: bool = False,
    ) -> None:
        self.http = http_client or JobreHttpClient(allow_private_urls=allow_private_urls)
        self.registry = registry or get_connector_registry()
        self.allow_private_urls = allow_private_urls

    def _infer_company_from_domain(self, url: str) -> str:
        dom = extract_canonical_domain(url)
        parts = dom.split(".")
        if len(parts) >= 2:
            return parts[0].replace("-", " ").title()
        return dom.title() or "Unknown Organization"

    async def discover_url(self, raw_url: str, *, probe_network: bool = True) -> SourceDiscoveryResult:
        clean_url = validate_public_url(
            raw_url,
            allow_private=self.allow_private_urls,
            resolve_dns=probe_network,
        )
        domain = extract_canonical_domain(clean_url)

        # Pass 1: Fast deterministic connector URL pattern checks (only high-specificity URLs)
        for key in self.registry.implemented_keys():
            connector = self.registry.get_connector(key)
            # Only run non-network URL regex check first for ATS connectors
            if connector.category == "ATS":
                res = await connector.discover(clean_url)
                if res.detected and res.confidence >= 0.90:
                    spec = self.registry.get_platform_spec(key)
                    return SourceDiscoveryResult(
                        input_url=clean_url,
                        canonical_source_url=res.canonical_source_url or clean_url,
                        canonical_domain=extract_canonical_domain(res.canonical_source_url or clean_url),
                        detected=True,
                        platform_key=key,
                        platform_name=spec.name if spec else connector.platform_name,
                        platform_category="ATS",
                        connector_implemented=True,
                        board_token=res.board_token,
                        company_name=res.company_name_hint or self._infer_company_from_domain(clean_url),
                        source_type="ATS_HOSTED_BOARD",
                        discovery_method="URL_PATTERN",
                        confidence=res.confidence,
                        evidence=res.evidence,
                    )

        # Pass 2: Check unimplemented catalog URL patterns (e.g., *.icims.com, *.eightfold.ai, workforcenow.adp.com)
        for spec in PLATFORM_CATALOG:
            if self.registry.has_connector(spec.connector_key):
                continue
            for pat in spec.url_patterns:
                m = re.search(pat, clean_url, flags=re.IGNORECASE)
                if m:
                    token = m.group(1) if m.lastindex and m.lastindex >= 1 else None
                    src_type = "INDEPENDENT_JOB_BOARD" if spec.category == "JOB_BOARD" else "ATS_HOSTED_BOARD"
                    return SourceDiscoveryResult(
                        input_url=clean_url,
                        canonical_source_url=clean_url,
                        canonical_domain=domain,
                        detected=True,
                        platform_key=spec.connector_key,
                        platform_name=spec.name,
                        platform_category=spec.category,
                        connector_implemented=False,
                        board_token=token,
                        company_name=(token or self._infer_company_from_domain(clean_url)).replace("-", " ").title(),
                        source_type=src_type,
                        discovery_method="CATALOG_URL_PATTERN",
                        confidence=0.92,
                        evidence=f"Matched {spec.name} URL pattern '{pat}'",
                    )

        if not probe_network:
            return SourceDiscoveryResult(
                input_url=clean_url,
                canonical_source_url=clean_url,
                canonical_domain=domain,
                detected=False,
                platform_key=None,
                platform_name=None,
                platform_category=None,
                connector_implemented=False,
                board_token=None,
                company_name=self._infer_company_from_domain(clean_url),
                source_type="COMPANY_CAREER_PAGE",
                discovery_method="STATIC_UNMATCHED",
                confidence=0.0,
                evidence="No deterministic URL signature matched without network inspection.",
            )

        # Pass 3: Live HTTP inspection for custom-domain job boards & embedded ATS career pages
        try:
            resp = await self.http.get(clean_url, headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
            final_url = resp.url
            html_body = resp.text
        except Exception as exc:
            return SourceDiscoveryResult(
                input_url=clean_url,
                canonical_source_url=clean_url,
                canonical_domain=domain,
                detected=False,
                platform_key=None,
                platform_name=None,
                platform_category=None,
                connector_implemented=False,
                board_token=None,
                company_name=self._infer_company_from_domain(clean_url),
                source_type="COMPANY_CAREER_PAGE",
                discovery_method="HTTP_PROBE_FAILED",
                confidence=0.0,
                evidence=f"HTTP probe error: {exc}",
            )

        # If redirect landed directly on an ATS board URL, re-check ATS connectors!
        if final_url != clean_url:
            for key in self.registry.implemented_keys():
                conn = self.registry.get_connector(key)
                if conn.category == "ATS":
                    res = await conn.discover(final_url)
                    if res.detected:
                        spec = self.registry.get_platform_spec(key)
                        return SourceDiscoveryResult(
                            input_url=clean_url,
                            canonical_source_url=res.canonical_source_url or final_url,
                            canonical_domain=extract_canonical_domain(res.canonical_source_url or final_url),
                            detected=True,
                            platform_key=key,
                            platform_name=spec.name if spec else conn.platform_name,
                            platform_category="ATS",
                            connector_implemented=True,
                            board_token=res.board_token,
                            company_name=res.company_name_hint or self._infer_company_from_domain(clean_url),
                            source_type="ATS_HOSTED_BOARD",
                            discovery_method="REDIRECT_RESOLUTION",
                            confidence=res.confidence,
                            evidence=f"Redirected to {final_url}; {res.evidence}",
                        )

        soup = BeautifulSoup(html_body, "html.parser")
        og_site = soup.find("meta", attrs={"property": "og:site_name"})
        title_tag = soup.find("title")
        company_guess = (
            (og_site.get("content", "").strip() if og_site else "")
            or (title_tag.get_text(" ", strip=True).split("|")[0].split("–")[0].split("-")[0].strip() if title_tag else "")
            or self._infer_company_from_domain(clean_url)
        )[:120]

        # Scan outbound links/iframes/scripts on page for embedded ATS boards (Greenhouse, Ashby, Lever, Workable, etc.)
        candidate_embedded_urls: list[str] = []
        for tag in soup.find_all(["a", "iframe", "script"], src=True):
            candidate_embedded_urls.append(urljoin(final_url, tag["src"]))
        for tag in soup.find_all("a", href=True):
            candidate_embedded_urls.append(urljoin(final_url, tag["href"]))

        for emb_url in candidate_embedded_urls:
            for key in self.registry.implemented_keys():
                conn = self.registry.get_connector(key)
                if conn.category != "ATS":
                    continue
                res = await conn.discover(emb_url)
                if res.detected and res.confidence >= 0.95:
                    spec = self.registry.get_platform_spec(key)
                    return SourceDiscoveryResult(
                        input_url=clean_url,
                        canonical_source_url=res.canonical_source_url or emb_url,
                        canonical_domain=extract_canonical_domain(res.canonical_source_url or emb_url),
                        detected=True,
                        platform_key=key,
                        platform_name=spec.name if spec else conn.platform_name,
                        platform_category="ATS",
                        connector_implemented=True,
                        board_token=res.board_token,
                        company_name=company_guess,
                        source_type="COMPANY_CAREER_PAGE",
                        discovery_method="EMBEDDED_ATS_LINK",
                        confidence=0.93,
                        evidence=f"Found embedded {conn.platform_name} link '{emb_url}' on page",
                    )

        # Check HTML signatures across all 78 platforms
        html_lower = html_body.lower()
        for spec in PLATFORM_CATALOG:
            matched_sigs = [sig for sig in spec.html_signatures if sig.lower() in html_lower]
            if matched_sigs:
                impl = self.registry.has_connector(spec.connector_key)
                canonical_target = final_url
                if spec.connector_key == "jobboard_io":
                    parsed_f = urlparse(final_url)
                    canonical_target = f"{parsed_f.scheme}://{parsed_f.netloc}/jobs.rss"
                elif spec.connector_key == "wp_job_manager":
                    parsed_f = urlparse(final_url)
                    canonical_target = f"{parsed_f.scheme}://{parsed_f.netloc}/wp-json/wp/v2/job-listings"

                conf = min(0.96, 0.84 + 0.05 * len(matched_sigs))
                return SourceDiscoveryResult(
                    input_url=clean_url,
                    canonical_source_url=canonical_target,
                    canonical_domain=extract_canonical_domain(canonical_target),
                    detected=True,
                    platform_key=spec.connector_key,
                    platform_name=spec.name,
                    platform_category=spec.category,
                    connector_implemented=impl,
                    board_token=None,
                    company_name=company_guess,
                    source_type="INDEPENDENT_JOB_BOARD" if spec.category == "JOB_BOARD" else "COMPANY_CAREER_PAGE",
                    discovery_method="HTML_SIGNATURE",
                    confidence=round(conf, 2),
                    evidence=f"Matched HTML signatures for {spec.name}: {', '.join(matched_sigs)}",
                )

        # Check if homepage has a /careers link worth one-hop inspection
        parsed_in = urlparse(clean_url)
        if parsed_in.path in ("", "/"):
            for a in soup.find_all("a", href=True):
                href_low = a["href"].lower()
                if any(h in href_low for h in CAREER_LINK_HINTS):
                    career_url = urljoin(final_url, a["href"])
                    if extract_canonical_domain(career_url) == domain and career_url != final_url:
                        sub = await self.discover_url(career_url, probe_network=True)
                        if sub.detected:
                            return sub
                        break

        return SourceDiscoveryResult(
            input_url=clean_url,
            canonical_source_url=final_url,
            canonical_domain=domain,
            detected=False,
            platform_key=None,
            platform_name=None,
            platform_category=None,
            connector_implemented=False,
            board_token=None,
            company_name=company_guess,
            source_type="COMPANY_CAREER_PAGE",
            discovery_method="UNIDENTIFIED",
            confidence=0.0,
            evidence="No known ATS or Job-Board signature detected with sufficient confidence.",
        )
