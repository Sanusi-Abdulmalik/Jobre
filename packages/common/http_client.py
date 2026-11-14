from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from packages.common.config import get_settings
from packages.common.metrics import CONNECTOR_HTTP_REQUESTS_TOTAL, CONNECTOR_LATENCY_SECONDS
from packages.common.security import SSRFSafetyError, validate_public_url

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
MAINTENANCE_URL_MARKERS = (
    "maintenance-page",
    "community.workday.com/maintenance",
    "/maintenance.html",
)


class HttpFetchError(RuntimeError):
    """Structured HTTP fetch error preserving status and retryability."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        retryable: bool = True,
        reason: str = "http_error",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.retryable = retryable
        self.reason = reason


@dataclass
class HttpResponseData:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    latency_ms: float

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        import orjson

        return orjson.loads(self.content)


@dataclass
class _DomainRateBucket:
    min_interval_sec: float
    last_request_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class JobreHttpClient:
    """SSRF-protected, rate-limited, retrying async HTTP client for connectors."""

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        default_rpm: int | None = None,
        allow_private_urls: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.timeout_seconds = timeout_seconds or settings.http_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.http_max_retries
        self.default_rpm = default_rpm or settings.default_rate_limit_rpm
        self.allow_private_urls = (
            allow_private_urls
            if allow_private_urls is not None
            else settings.allow_private_network_urls
        )
        self.user_agent = settings.jobre_user_agent
        self._transport = transport
        self._buckets: dict[str, _DomainRateBucket] = {}

    async def _throttle(self, domain: str, rpm: int | None = None) -> None:
        effective_rpm = max(1, rpm or self.default_rpm)
        min_interval = 60.0 / float(effective_rpm)
        bucket = self._buckets.get(domain)
        if bucket is None:
            bucket = _DomainRateBucket(min_interval_sec=min_interval)
            self._buckets[domain] = bucket
        else:
            bucket.min_interval_sec = min_interval

        async with bucket.lock:
            now = time.monotonic()
            elapsed = now - bucket.last_request_at
            if elapsed < bucket.min_interval_sec:
                await asyncio.sleep(bucket.min_interval_sec - elapsed)
            bucket.last_request_at = time.monotonic()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        data: Any | None = None,
        rate_limit_rpm: int | None = None,
        max_redirects: int = 5,
    ) -> HttpResponseData:
        validate_public_url(
            url,
            allow_private=self.allow_private_urls,
            resolve_dns=self._transport is None,
        )

        merged_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            merged_headers.update(headers)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            current_url = url
            current_method = method.upper()
            current_json = json_body
            current_data = data
            current_params = params

            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout_seconds),
                    follow_redirects=False,
                    transport=self._transport,
                ) as client:
                    for _hop in range(max_redirects + 1):
                        domain = (urlparse(current_url).hostname or "unknown").lower()
                        await self._throttle(domain, rate_limit_rpm)

                        t0 = time.perf_counter()
                        resp = await client.request(
                            current_method,
                            current_url,
                            headers=merged_headers,
                            params=current_params,
                            json=current_json,
                            data=current_data,
                        )
                        latency_s = time.perf_counter() - t0
                        CONNECTOR_HTTP_REQUESTS_TOTAL.labels(
                            domain=domain, status_code=str(resp.status_code)
                        ).inc()
                        CONNECTOR_LATENCY_SECONDS.labels(domain=domain).observe(latency_s)

                        if resp.status_code in (301, 302, 303, 307, 308):
                            location = resp.headers.get("location")
                            if not location:
                                break
                            next_url = urljoin(str(resp.url), location)
                            lower_next = next_url.lower()
                            if any(marker in lower_next for marker in MAINTENANCE_URL_MARKERS):
                                raise HttpFetchError(
                                    f"Upstream platform is in scheduled maintenance ({next_url})",
                                    status_code=503,
                                    url=current_url,
                                    retryable=True,
                                    reason="maintenance_window",
                                )
                            validate_public_url(
                                next_url,
                                allow_private=self.allow_private_urls,
                                resolve_dns=self._transport is None,
                            )
                            current_url = next_url
                            current_params = None
                            if resp.status_code == 303 or (
                                resp.status_code in (301, 302) and current_method == "POST"
                            ):
                                current_method = "GET"
                                current_json = None
                                current_data = None
                            continue
                        break
                    else:
                        raise HttpFetchError(
                            f"Exceeded max redirects ({max_redirects}) for {url}",
                            status_code=310,
                            url=url,
                            retryable=False,
                            reason="too_many_redirects",
                        )

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = resp.headers.get("retry-after")
                    if attempt < self.max_retries:
                        delay = (
                            min(float(retry_after), 15.0)
                            if retry_after and retry_after.isdigit()
                            else (0.6 * (2**attempt) + random.uniform(0.05, 0.35))
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise HttpFetchError(
                        f"HTTP {resp.status_code} from {current_url} after {attempt + 1} attempts",
                        status_code=resp.status_code,
                        url=current_url,
                        retryable=True,
                        reason="rate_limited" if resp.status_code == 429 else "upstream_5xx",
                    )

                if resp.status_code >= 400:
                    raise HttpFetchError(
                        f"HTTP {resp.status_code} from {current_url}",
                        status_code=resp.status_code,
                        url=current_url,
                        retryable=False,
                        reason=f"http_{resp.status_code}",
                    )

                return HttpResponseData(
                    url=str(resp.url),
                    status_code=resp.status_code,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    content=resp.content,
                    latency_ms=round(latency_s * 1000.0, 2),
                )

            except SSRFSafetyError:
                raise
            except HttpFetchError as exc:
                last_exc = exc
                if not exc.retryable or attempt >= self.max_retries:
                    raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    delay = 0.6 * (2**attempt) + random.uniform(0.05, 0.35)
                    await asyncio.sleep(delay)
                    continue
                raise HttpFetchError(
                    f"Network/timeout failure fetching {url}: {exc}",
                    status_code=None,
                    url=url,
                    retryable=True,
                    reason="network_timeout",
                ) from exc

        raise HttpFetchError(
            f"Failed to fetch {url}: {last_exc}",
            url=url,
            retryable=True,
            reason="exhausted_retries",
        )

    async def get(self, url: str, **kwargs: Any) -> HttpResponseData:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> HttpResponseData:
        return await self.request("POST", url, **kwargs)
