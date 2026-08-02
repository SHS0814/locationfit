from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.core.ai_security import AIProtectionError
from backend.app.services.agent_service import (
    AgentStateError,
    AgentTimeoutError,
    AgentUnavailableError,
)
from backend.app.services.store_service import StoreDataUnavailableError, StoreUpstreamError

logger = logging.getLogger("kb_recommender.errors")
PUBLIC_RUNTIME_ERROR_MESSAGE = "서비스를 일시적으로 사용할 수 없습니다."


def error_response(status_code: int, code: str, message: str, request_id: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


async def ai_protection_error_handler(request: Request, exc: AIProtectionError) -> JSONResponse:
    response = error_response(
        exc.status_code,
        exc.code,
        exc.message,
        getattr(request.state, "request_id", None),
    )
    if exc.retry_after is not None:
        response.headers["Retry-After"] = str(exc.retry_after)
    return response


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    message = str(exc)
    code = "NO_ELIGIBLE_CANDIDATES" if "추천 후보가 없습니다" in message else "INVALID_RECOMMENDATION_REQUEST"
    return error_response(422, code, message, getattr(request.state, "request_id", None))


async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled runtime error request_id=%s method=%s path=%s error_type=%s",
        request_id,
        request.method,
        request.url.path,
        type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return error_response(
        503,
        "RECOMMENDER_UNAVAILABLE",
        PUBLIC_RUNTIME_ERROR_MESSAGE,
        request_id,
    )


async def agent_unavailable_error_handler(request: Request, exc: AgentUnavailableError) -> JSONResponse:
    return error_response(
        503,
        "AGENT_UNAVAILABLE",
        str(exc),
        getattr(request.state, "request_id", None),
    )


async def agent_timeout_error_handler(request: Request, exc: AgentTimeoutError) -> JSONResponse:
    return error_response(
        504,
        "AGENT_TIMEOUT",
        str(exc),
        getattr(request.state, "request_id", None),
    )


async def agent_state_error_handler(request: Request, exc: AgentStateError) -> JSONResponse:
    return error_response(
        422,
        "INVALID_AGENT_STATE",
        str(exc),
        getattr(request.state, "request_id", None),
    )


async def store_data_unavailable_error_handler(
    request: Request, exc: StoreDataUnavailableError,
) -> JSONResponse:
    return error_response(
        503,
        "STORE_DATA_UNAVAILABLE",
        str(exc),
        getattr(request.state, "request_id", None),
    )


async def store_upstream_error_handler(request: Request, exc: StoreUpstreamError) -> JSONResponse:
    return error_response(
        502,
        "STORE_UPSTREAM_ERROR",
        str(exc),
        getattr(request.state, "request_id", None),
    )


async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(value) for value in first.get("loc", []) if value != "body")
    message = str(first.get("msg", "입력값을 확인해주세요."))
    if location:
        message = f"{location}: {message}"
    return error_response(
        422,
        "REQUEST_SCHEMA_VALIDATION_FAILED",
        message,
        getattr(request.state, "request_id", None),
    )
