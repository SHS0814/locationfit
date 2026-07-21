from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.services.agent_service import (
    AgentStateError,
    AgentTimeoutError,
    AgentUnavailableError,
)
from backend.app.services.store_service import StoreDataUnavailableError, StoreUpstreamError


def error_response(status_code: int, code: str, message: str, request_id: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    message = str(exc)
    if request.url.path.endswith("/lease-candidates/extract"):
        code = "INVALID_LEASE_CANDIDATE_SOURCE"
    else:
        code = "NO_ELIGIBLE_CANDIDATES" if "추천 후보가 없습니다" in message else "INVALID_RECOMMENDATION_REQUEST"
    return error_response(422, code, message, getattr(request.state, "request_id", None))


async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    return error_response(
        503,
        "RECOMMENDER_UNAVAILABLE",
        str(exc),
        getattr(request.state, "request_id", None),
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
