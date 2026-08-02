from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response

from backend.app.core.ai_security import (
    AI_SESSION_COOKIE,
    AIProtectionError,
    create_ai_session,
    get_ai_security_settings,
    read_ai_session,
    validate_ai_security_configuration,
)
from backend.app.core.config import Settings
from backend.app.schemas.security import AIAccessRequest, AISessionStatus

router = APIRouter(tags=["ai-access"])


@router.get("/ai/session", response_model=AISessionStatus)
async def ai_session_status(
    request: Request,
    config: Settings = Depends(get_ai_security_settings),
) -> AISessionStatus:
    principal = read_ai_session(request, config)
    return AISessionStatus(
        required=config.ai_security_enabled,
        authenticated=principal is not None,
        expires_at=principal.expires_at if principal else None,
    )


@router.post("/ai/session", response_model=AISessionStatus)
async def create_ai_session_endpoint(
    payload: AIAccessRequest,
    response: Response,
    config: Settings = Depends(get_ai_security_settings),
) -> AISessionStatus:
    validate_ai_security_configuration(config)
    if not config.ai_security_enabled:
        return AISessionStatus(required=False, authenticated=True, expires_at=None)
    if not secrets.compare_digest(
        payload.access_code.encode("utf-8"),
        config.ai_access_code.encode("utf-8"),
    ):
        raise AIProtectionError(401, "INVALID_AI_ACCESS_CODE", "접근 코드가 올바르지 않습니다.")
    token, expires_at = create_ai_session(config)
    response.set_cookie(
        AI_SESSION_COOKIE,
        token,
        max_age=config.ai_session_ttl_seconds,
        expires=expires_at,
        path="/api/v1",
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )
    return AISessionStatus(required=True, authenticated=True, expires_at=expires_at)


@router.delete("/ai/session", status_code=204, response_class=Response)
async def delete_ai_session(response: Response) -> Response:
    response.delete_cookie(AI_SESSION_COOKIE, path="/api/v1")
    response.status_code = 204
    return response
