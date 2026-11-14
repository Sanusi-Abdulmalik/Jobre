from __future__ import annotations

import collections
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SlidingWindowRateLimitMiddleware(BaseHTTPMiddleware):
    """Lightweight per-IP sliding window rate limiter for API protection."""

    def __init__(self, app, max_requests_per_minute: int = 240) -> None:
        super().__init__(app)
        self.max_rpm = max_requests_per_minute
        self._hits: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in ("/api/v1/health", "/metrics"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60.0
        q = self._hits[client_ip]
        while q and q[0] < window_start:
            q.popleft()

        if len(q) >= self.max_rpm:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down requests."},
                headers={"Retry-After": "15"},
            )
        q.append(now)
        return await call_next(request)
