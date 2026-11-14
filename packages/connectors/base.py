from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

from packages.common.http_client import HttpFetchError, JobreHttpClient
from packages.normalization.engine import NormalizedJobInput


@dataclass
class ConnectorSourceConfig:
    source_id: str
    source_name: str
    source_url: str
    company_name: str
    board_token: str | None = None
    rate_limit_rpm: int = 30
    extra_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryProbeResult:
    detected: bool
    platform_key: str
    confidence: float
    board_token: str | None = None
    canonical_source_url: str | None = None
    company_name_hint: str | None = None
    evidence: str = ""


@dataclass
class RawJobPayload:
    external_job_id: str
    raw_data: dict[str, Any]
    source_url: str


@dataclass
class FetchBatchResult:
    jobs: list[RawJobPayload]
    next_cursor: str | None = None
    http_status: int = 200
    is_complete: bool = True
    request_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorHealthResult:
    healthy: bool
    status_code: int | None
    latency_ms: float
    message: str


class BaseConnector(ABC):
    """Abstract base interface implemented by all Jobre platform connectors."""

    connector_key: str = "base"
    platform_name: str = "Base"
    category: str = "ATS"  # ATS | JOB_BOARD
    extraction_version: str = "1.0.0"
    default_rate_limit_rpm: int = 30

    def __init__(self, http_client: JobreHttpClient | None = None) -> None:
        self.http = http_client or JobreHttpClient(default_rpm=self.default_rate_limit_rpm)

    @abstractmethod
    async def discover(self, source_url: str) -> DiscoveryProbeResult:
        """Inspect a candidate URL and determine if it belongs to this platform."""

    @abstractmethod
    async def fetch_jobs(
        self,
        source: ConnectorSourceConfig,
        cursor: str | None = None,
    ) -> FetchBatchResult:
        """Fetch one page/batch of raw job listings from the public platform interface."""

    @abstractmethod
    def normalize(
        self,
        raw_job: dict[str, Any],
        source: ConnectorSourceConfig,
    ) -> NormalizedJobInput:
        """Transform a raw platform job payload into the canonical Jobre schema."""

    async def health_check(self, source: ConnectorSourceConfig) -> ConnectorHealthResult:
        """Execute a lightweight live probe against the configured source."""
        try:
            batch = await self.fetch_jobs(source, cursor=None)
            return ConnectorHealthResult(
                healthy=True,
                status_code=batch.http_status,
                latency_ms=float(batch.request_metadata.get("latency_ms", 0.0)),
                message=f"OK ({len(batch.jobs)} jobs in initial batch)",
            )
        except HttpFetchError as exc:
            return ConnectorHealthResult(
                healthy=False,
                status_code=exc.status_code,
                latency_ms=0.0,
                message=str(exc),
            )
        except Exception as exc:
            return ConnectorHealthResult(
                healthy=False,
                status_code=None,
                latency_ms=0.0,
                message=f"Unexpected health check error: {exc}",
            )


def extract_jsonld_job_posting(html_text: str) -> dict[str, Any] | None:
    """Extract schema.org JobPosting JSON-LD block from a public HTML job page if present."""
    soup = BeautifulSoup(html_text, "html.parser")
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        content = (script.string or script.get_text() or "").strip()
        if not content:
            continue
        try:
            parsed = json.loads(content)
        except Exception:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "JobPosting" or (
                isinstance(item.get("@type"), list) and "JobPosting" in item["@type"]
            ):
                return item
            graph = item.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and node.get("@type") == "JobPosting":
                        return node
    return None
