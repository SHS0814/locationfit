from dataclasses import replace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1 import security
from backend.app.core.ai_security import (
    AIProtectionError,
    AISessionPrincipal,
    _enforce_ai_limits,
    get_ai_security_settings,
    require_ai_session,
    validate_ai_security_configuration,
)
from backend.app.core.config import Settings, settings
from backend.app.core.errors import ai_protection_error_handler


def _secure_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "development",
        "ai_security_enabled": True,
        "ai_access_code": "a" * 24,
        "ai_session_secret": "b" * 64,
        "ai_session_ttl_seconds": 3_600,
        "database_url": "postgresql+psycopg://test:test@db:5432/test",
    }
    values.update(overrides)
    return replace(settings, **values)


def _test_app(config: Settings) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_ai_security_settings] = lambda: config
    app.add_exception_handler(AIProtectionError, ai_protection_error_handler)
    app.include_router(security.router, prefix="/api/v1")

    @app.get("/api/v1/protected")
    async def protected(
        principal: AISessionPrincipal = Depends(require_ai_session),
    ) -> dict[str, str]:
        return {"session": principal.session_id_hash}

    return app


def _mutable_settings_app(holder: dict[str, Settings]) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_ai_security_settings] = lambda: holder["config"]
    app.add_exception_handler(AIProtectionError, ai_protection_error_handler)
    app.include_router(security.router, prefix="/api/v1")
    return app


def test_ai_session_requires_valid_access_code_and_sets_http_only_cookie() -> None:
    with TestClient(_test_app(_secure_settings())) as client:
        initial = client.get("/api/v1/ai/session")
        unauthenticated = client.get("/api/v1/protected")
        rejected = client.post("/api/v1/ai/session", json={"access_code": "wrong"})
        accepted = client.post("/api/v1/ai/session", json={"access_code": "a" * 24})
        authenticated = client.get("/api/v1/protected")

    assert initial.json() == {"required": True, "authenticated": False, "expires_at": None}
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AI_AUTH_REQUIRED"
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "INVALID_AI_ACCESS_CODE"
    assert accepted.status_code == 200
    cookie = accepted.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "a" * 24 not in cookie
    assert authenticated.status_code == 200
    assert len(authenticated.json()["session"]) == 64


def test_ai_session_cookie_is_secure_in_production() -> None:
    with TestClient(_test_app(_secure_settings(app_env="production"))) as client:
        response = client.post("/api/v1/ai/session", json={"access_code": "a" * 24})

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_rotating_access_code_invalidates_existing_sessions() -> None:
    holder = {"config": _secure_settings()}
    with TestClient(_mutable_settings_app(holder)) as client:
        accepted = client.post("/api/v1/ai/session", json={"access_code": "a" * 24})
        holder["config"] = _secure_settings(ai_access_code="c" * 24)
        status = client.get("/api/v1/ai/session")

    assert accepted.status_code == 200
    assert status.json()["authenticated"] is False


def test_ai_security_cannot_be_disabled_in_production() -> None:
    config = _secure_settings(app_env="production", ai_security_enabled=False)

    with pytest.raises(AIProtectionError) as caught:
        validate_ai_security_configuration(config)

    assert caught.value.code == "AI_SECURITY_MISCONFIGURED"


def test_ai_security_rejects_short_server_secrets() -> None:
    config = _secure_settings(ai_access_code="short", ai_session_secret="short")

    with pytest.raises(AIProtectionError) as caught:
        validate_ai_security_configuration(config)

    assert caught.value.code == "AI_SECURITY_MISCONFIGURED"


def test_ai_security_rejects_wildcard_cors() -> None:
    config = _secure_settings(cors_origins=("*",))

    with pytest.raises(AIProtectionError) as caught:
        validate_ai_security_configuration(config)

    assert caught.value.code == "AI_SECURITY_MISCONFIGURED"


@pytest.mark.parametrize(
    ("counts", "expected_code"),
    [
        ({"minute_count": 10}, "AI_GLOBAL_RATE_LIMIT_EXCEEDED"),
        ({"active_count": 2}, "AI_CONCURRENCY_LIMIT_EXCEEDED"),
        ({"daily_count": 100}, "AI_DAILY_BUDGET_EXCEEDED"),
        ({"daily_reserved_microusd": 4_950_001}, "AI_DAILY_BUDGET_EXCEEDED"),
    ],
)
def test_ai_usage_limits_reject_each_shared_boundary(
    counts: dict[str, int], expected_code: str,
) -> None:
    values = {
        "minute_count": 0,
        "active_count": 0,
        "daily_count": 0,
        "daily_reserved_microusd": 0,
        "request_reservation_microusd": 50_000,
        "daily_budget_microusd": 5_000_000,
    }
    values.update(counts)

    with pytest.raises(AIProtectionError) as caught:
        _enforce_ai_limits(_secure_settings(), **values)

    assert caught.value.code == expected_code


def test_ai_usage_limits_allow_exact_daily_budget_boundary() -> None:
    _enforce_ai_limits(
        _secure_settings(),
        minute_count=9,
        active_count=1,
        daily_count=99,
        daily_reserved_microusd=4_950_000,
        request_reservation_microusd=50_000,
        daily_budget_microusd=5_000_000,
    )
