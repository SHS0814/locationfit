from __future__ import annotations

import logging
import math
import re
from collections import defaultdict, deque
from time import monotonic, perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.core.errors import error_response

logger = logging.getLogger("kb_recommender.request")
STORE_LOOKUP_PATH = re.compile(r"/areas/[^/]+/stores/?$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id") or str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        content_length = headers.get("content-length")
        try:
            declared_bytes = int(content_length) if content_length else None
        except ValueError:
            declared_bytes = None

        started = perf_counter()
        status_code = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
                response_headers["X-Process-Time-Ms"] = f"{(perf_counter() - started) * 1000:.2f}"
            await send(message)

        async def reject_oversized_request() -> None:
            response = error_response(
                413,
                "REQUEST_TOO_LARGE",
                "요청 본문이 너무 큽니다.",
                request_id,
            )
            await response(scope, receive, send_with_context)

        if declared_bytes is not None and declared_bytes > self.max_request_bytes:
            await reject_oversized_request()
        else:
            buffered_messages: deque[Message] = deque()
            received_bytes = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    buffered_messages.append(message)
                    break
                if message["type"] != "http.request":
                    buffered_messages.append(message)
                    continue

                chunk = message.get("body", b"")
                received_bytes += len(chunk)
                if received_bytes > self.max_request_bytes:
                    await reject_oversized_request()
                    break
                buffered_messages.append(message)
                if not message.get("more_body", False):
                    break

            if received_bytes <= self.max_request_bytes:

                async def replay_receive() -> Message:
                    if buffered_messages:
                        return buffered_messages.popleft()
                    return await receive()

                await self.app(scope, replay_receive, send_with_context)

        elapsed_ms = (perf_counter() - started) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
            request_id,
            scope["method"],
            scope["path"],
            status_code,
            elapsed_ms,
        )


class RecommendationRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limit: int,
        agent_limit: int,
        store_limit: int = 5,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.limit = limit
        self.agent_limit = agent_limit
        self.store_limit = store_limit
        self.window_seconds = window_seconds
        self.requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path.endswith("/recommendations"):
            bucket, limit, code = "recommendations", self.limit, "RATE_LIMIT_EXCEEDED"
        elif request.method == "POST" and request.url.path.endswith(
            ("/agent/turns", "/agent/workspace-turns", "/agent/web-research")
        ):
            bucket, limit, code = "agent", self.agent_limit, "AGENT_RATE_LIMIT_EXCEEDED"
        elif request.method == "GET" and STORE_LOOKUP_PATH.search(request.url.path):
            bucket, limit, code = "stores", self.store_limit, "STORE_RATE_LIMIT_EXCEEDED"
        else:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = monotonic()
        history = self.requests[(client, bucket)]
        while history and history[0] <= now - self.window_seconds:
            history.popleft()
        if len(history) >= limit:
            response = error_response(
                429,
                code,
                "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
                getattr(request.state, "request_id", None),
            )
            retry_after = max(1, math.ceil(history[0] + self.window_seconds - now))
            response.headers["Retry-After"] = str(retry_after)
            return response
        history.append(now)
        return await call_next(request)
