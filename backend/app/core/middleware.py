from __future__ import annotations

from collections import defaultdict, deque
import logging
from time import monotonic, perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.errors import error_response


logger = logging.getLogger("kb_recommender.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_request_bytes: int) -> None:
        super().__init__(app)
        self.max_request_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        try:
            request_bytes = int(content_length) if content_length else 0
        except ValueError:
            request_bytes = 0
        if request_bytes > self.max_request_bytes:
            return error_response(413, "REQUEST_TOO_LARGE", "요청 본문이 너무 큽니다.", request_id)
        started = perf_counter()
        response = await call_next(request)
        elapsed_ms = (perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        logger.info(
            "request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


class RecommendationRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limit: int, agent_limit: int, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.agent_limit = agent_limit
        self.window_seconds = window_seconds
        self.requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)
        if request.url.path.endswith("/recommendations"):
            bucket, limit, code = "recommendations", self.limit, "RATE_LIMIT_EXCEEDED"
        elif request.url.path.endswith(("/agent/turns", "/agent/workspace-turns", "/agent/web-research")):
            bucket, limit, code = "agent", self.agent_limit, "AGENT_RATE_LIMIT_EXCEEDED"
        else:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = monotonic()
        history = self.requests[(client, bucket)]
        while history and history[0] <= now - self.window_seconds:
            history.popleft()
        if len(history) >= limit:
            return error_response(
                429,
                code,
                "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
                getattr(request.state, "request_id", None),
            )
        history.append(now)
        return await call_next(request)
