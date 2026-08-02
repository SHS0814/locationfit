from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import Settings, settings
from backend.app.db.models import AIRequestEvent
from backend.app.db.session import session_scope

logger = logging.getLogger("kb_recommender.ai_security")

AI_SESSION_COOKIE = "locationfit_ai_session"
AI_GUARD_ADVISORY_LOCK_ID = 1_263_225_161
MICRO_USD = Decimal("1000000")


class AIProtectionError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class AISessionPrincipal:
    session_id_hash: str
    expires_at: datetime | None


@dataclass(frozen=True)
class AIRequestPermit:
    event_id: UUID


def get_ai_security_settings() -> Settings:
    return settings


def validate_ai_security_configuration(config: Settings) -> None:
    if not config.ai_security_enabled:
        if config.app_env == "production":
            raise AIProtectionError(
                503,
                "AI_SECURITY_MISCONFIGURED",
                "운영 환경에서는 AI 보안 기능을 비활성화할 수 없습니다.",
            )
        return
    if len(config.ai_access_code) < 20 or len(config.ai_session_secret) < 32:
        raise AIProtectionError(
            503,
            "AI_SECURITY_MISCONFIGURED",
            "AI 접근 보안 설정이 완료되지 않았습니다.",
        )
    if not config.database_url:
        raise AIProtectionError(
            503,
            "AI_SECURITY_MISCONFIGURED",
            "AI 요청 보호에는 PostgreSQL DATABASE_URL이 필요합니다.",
        )
    if "*" in config.cors_origins:
        raise AIProtectionError(
            503,
            "AI_SECURITY_MISCONFIGURED",
            "AI 세션 인증에서는 와일드카드 CORS_ORIGINS를 사용할 수 없습니다.",
        )
    numeric_values = (
        config.ai_session_ttl_seconds,
        config.ai_global_rate_limit_per_minute,
        config.ai_daily_request_limit,
        config.ai_max_concurrent_requests,
        config.ai_lease_timeout_seconds,
    )
    if any(value <= 0 for value in numeric_values) or config.ai_daily_budget_usd <= 0:
        raise AIProtectionError(
            503,
            "AI_SECURITY_MISCONFIGURED",
            "AI 사용량 제한 설정은 0보다 커야 합니다.",
        )


def create_ai_session(config: Settings, *, now: datetime | None = None) -> tuple[str, datetime]:
    validate_ai_security_configuration(config)
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=config.ai_session_ttl_seconds)
    nonce = secrets.token_urlsafe(24)
    payload = f"v1.{int(issued_at.timestamp())}.{int(expires_at.timestamp())}.{nonce}"
    signature = hmac.new(
        _session_signing_key(config),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}", expires_at


def read_ai_session(
    request: Request,
    config: Settings,
    *,
    now: datetime | None = None,
) -> AISessionPrincipal | None:
    validate_ai_security_configuration(config)
    if not config.ai_security_enabled:
        return AISessionPrincipal(session_id_hash="security-disabled", expires_at=None)
    token = request.cookies.get(AI_SESSION_COOKIE)
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 5 or parts[0] != "v1":
        return None
    _, issued_raw, expires_raw, nonce, provided_signature = parts
    payload = ".".join(parts[:4])
    expected_signature = hmac.new(
        _session_signing_key(config),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None
    try:
        issued_at = datetime.fromtimestamp(int(issued_raw), UTC)
        expires_at = datetime.fromtimestamp(int(expires_raw), UTC)
    except (OverflowError, ValueError):
        return None
    current = now or datetime.now(UTC)
    if expires_at <= current or issued_at > current + timedelta(minutes=1):
        return None
    return AISessionPrincipal(
        session_id_hash=hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        expires_at=expires_at,
    )


def require_ai_session(
    request: Request,
    config: Settings = Depends(get_ai_security_settings),
) -> AISessionPrincipal:
    principal = read_ai_session(request, config)
    if principal is None:
        raise AIProtectionError(
            401,
            "AI_AUTH_REQUIRED",
            "AI 기능을 사용하려면 접근 코드를 입력해주세요.",
        )
    return principal


class AIUsageLimiter:
    def __init__(self, config: Settings) -> None:
        self.config = config

    def acquire(self, *, endpoint: str, principal: AISessionPrincipal) -> AIRequestPermit:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=self.config.ai_lease_timeout_seconds)
        reserved_cost = _reservation_microusd(self.config, endpoint)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        minute_start = now - timedelta(minutes=1)
        event_id = uuid4()

        with session_scope() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": AI_GUARD_ADVISORY_LOCK_ID},
            )
            minute_count = session.scalar(
                select(func.count())
                .select_from(AIRequestEvent)
                .where(AIRequestEvent.started_at >= minute_start)
            ) or 0

            active_count = session.scalar(
                select(func.count())
                .select_from(AIRequestEvent)
                .where(
                    AIRequestEvent.finished_at.is_(None),
                    AIRequestEvent.lease_expires_at > now,
                )
            ) or 0

            daily_count, daily_reserved = session.execute(
                select(
                    func.count(AIRequestEvent.id),
                    func.coalesce(func.sum(AIRequestEvent.reserved_cost_microusd), 0),
                ).where(
                    AIRequestEvent.started_at >= day_start,
                    AIRequestEvent.started_at < day_end,
                )
            ).one()
            daily_budget = _usd_to_microusd(self.config.ai_daily_budget_usd)
            _enforce_ai_limits(
                self.config,
                minute_count=minute_count,
                active_count=active_count,
                daily_count=daily_count,
                daily_reserved_microusd=daily_reserved,
                request_reservation_microusd=reserved_cost,
                daily_budget_microusd=daily_budget,
            )

            session.add(AIRequestEvent(
                id=event_id,
                session_id_hash=principal.session_id_hash,
                endpoint=endpoint,
                reserved_cost_microusd=reserved_cost,
                started_at=now,
                lease_expires_at=lease_expires_at,
            ))
        return AIRequestPermit(event_id=event_id)

    def release(self, permit: AIRequestPermit) -> None:
        with session_scope() as session:
            session.execute(
                update(AIRequestEvent)
                .where(AIRequestEvent.id == permit.event_id)
                .values(finished_at=datetime.now(UTC))
            )


def require_ai_request(
    request: Request,
    principal: AISessionPrincipal = Depends(require_ai_session),
    config: Settings = Depends(get_ai_security_settings),
) -> Generator[AIRequestPermit | None, None, None]:
    if not config.ai_security_enabled:
        yield None
        return
    endpoint = _endpoint_kind(request.url.path)
    limiter = AIUsageLimiter(config)
    try:
        permit = limiter.acquire(endpoint=endpoint, principal=principal)
    except AIProtectionError:
        raise
    except (RuntimeError, SQLAlchemyError) as exc:
        logger.exception("AI request guard database failure")
        raise AIProtectionError(
            503,
            "AI_GUARD_UNAVAILABLE",
            "AI 사용량 보호 장치를 확인할 수 없어 요청을 차단했습니다.",
        ) from exc
    try:
        yield permit
    finally:
        try:
            limiter.release(permit)
        except (RuntimeError, SQLAlchemyError):
            logger.exception("Failed to release AI request lease event_id=%s", permit.event_id)


def _endpoint_kind(path: str) -> str:
    normalized = path.rstrip("/")
    if normalized.endswith("/agent/turns"):
        return "agent"
    if normalized.endswith("/agent/workspace-turns"):
        return "workspace"
    if normalized.endswith("/agent/web-research"):
        return "web_research"
    raise AIProtectionError(500, "AI_GUARD_ROUTE_UNKNOWN", "AI 보호 경로 설정을 확인해주세요.")


def _reservation_microusd(config: Settings, endpoint: str) -> int:
    reservations = {
        "agent": config.ai_agent_request_reservation_usd,
        "workspace": config.ai_workspace_request_reservation_usd,
        "web_research": config.ai_web_research_request_reservation_usd,
    }
    reservation = reservations[endpoint]
    if reservation <= 0:
        raise AIProtectionError(
            503,
            "AI_SECURITY_MISCONFIGURED",
            "AI 요청 비용 예약값은 0보다 커야 합니다.",
        )
    return _usd_to_microusd(reservation)


def _enforce_ai_limits(
    config: Settings,
    *,
    minute_count: int,
    active_count: int,
    daily_count: int,
    daily_reserved_microusd: int,
    request_reservation_microusd: int,
    daily_budget_microusd: int,
) -> None:
    if minute_count >= config.ai_global_rate_limit_per_minute:
        raise AIProtectionError(
            429,
            "AI_GLOBAL_RATE_LIMIT_EXCEEDED",
            "전체 AI 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
            retry_after=60,
        )
    if active_count >= config.ai_max_concurrent_requests:
        raise AIProtectionError(
            429,
            "AI_CONCURRENCY_LIMIT_EXCEEDED",
            "현재 처리 중인 AI 요청이 많습니다. 잠시 후 다시 시도해주세요.",
            retry_after=5,
        )
    if (
        daily_count >= config.ai_daily_request_limit
        or daily_reserved_microusd + request_reservation_microusd > daily_budget_microusd
    ):
        raise AIProtectionError(
            429,
            "AI_DAILY_BUDGET_EXCEEDED",
            "오늘의 AI 사용 한도에 도달했습니다. 다음 UTC 일자에 다시 시도해주세요.",
        )


def _usd_to_microusd(value: Decimal) -> int:
    return int((value * MICRO_USD).to_integral_value(rounding=ROUND_CEILING))


def _session_signing_key(config: Settings) -> bytes:
    return hmac.new(
        config.ai_session_secret.encode("utf-8"),
        config.ai_access_code.encode("utf-8"),
        hashlib.sha256,
    ).digest()
