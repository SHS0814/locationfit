from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


def _bool_env(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "로케이션핏 API")
    app_env: str = os.getenv("APP_ENV", "development")
    api_prefix: str = "/api/v1"
    database_url: str | None = os.getenv("DATABASE_URL") or None
    bizinfo_api_key: str = os.getenv("BIZINFO_API_KEY", "")
    artifact_dir: Path = Path(
        os.getenv("ARTIFACT_DIR", str(PROJECT_ROOT / "backend/artifacts/current"))
    ).resolve()
    cors_origins: tuple[str, ...] = _csv_env(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    agent_rate_limit_per_minute: int = int(os.getenv("AGENT_RATE_LIMIT_PER_MINUTE", "10"))
    ai_security_enabled: bool = _bool_env("AI_SECURITY_ENABLED", "true")
    ai_access_code: str = os.getenv("AI_ACCESS_CODE", "")
    ai_session_secret: str = os.getenv("AI_SESSION_SECRET", "")
    ai_session_ttl_seconds: int = int(os.getenv("AI_SESSION_TTL_SECONDS", "28800"))
    ai_global_rate_limit_per_minute: int = int(
        os.getenv("AI_GLOBAL_RATE_LIMIT_PER_MINUTE", "10")
    )
    ai_daily_request_limit: int = int(os.getenv("AI_DAILY_REQUEST_LIMIT", "100"))
    ai_daily_budget_usd: Decimal = Decimal(os.getenv("AI_DAILY_BUDGET_USD", "5.00"))
    ai_max_concurrent_requests: int = int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "2"))
    ai_lease_timeout_seconds: int = int(os.getenv("AI_LEASE_TIMEOUT_SECONDS", "120"))
    ai_agent_request_reservation_usd: Decimal = Decimal(
        os.getenv("AI_AGENT_REQUEST_RESERVATION_USD", "0.10")
    )
    ai_workspace_request_reservation_usd: Decimal = Decimal(
        os.getenv("AI_WORKSPACE_REQUEST_RESERVATION_USD", "0.20")
    )
    ai_web_research_request_reservation_usd: Decimal = Decimal(
        os.getenv("AI_WEB_RESEARCH_REQUEST_RESERVATION_USD", "0.25")
    )
    store_rate_limit_per_minute: int = int(os.getenv("STORE_RATE_LIMIT_PER_MINUTE", "5"))
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    agent_timeout_seconds: float = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
    workspace_agent_timeout_seconds: float = float(
        os.getenv("WORKSPACE_AGENT_TIMEOUT_SECONDS", "60")
    )
    web_research_timeout_seconds: float = float(os.getenv("WEB_RESEARCH_TIMEOUT_SECONDS", "45"))
    agent_max_turns: int = int(os.getenv("AGENT_MAX_TURNS", "4"))
    max_request_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", str(32 * 1024)))
    data_go_kr_service_key: str = os.getenv("DATA_GO_KR_SERVICE_KEY", "")
    sbiz_store_api_base_url: str = os.getenv(
        "SBIZ_STORE_API_BASE_URL", "https://apis.data.go.kr/B553077/api/open/sdsc2"
    ).rstrip("/")
    store_cache_ttl_seconds: float = float(os.getenv("STORE_CACHE_TTL_SECONDS", "86400"))
    store_stale_ttl_seconds: float = float(os.getenv("STORE_STALE_TTL_SECONDS", "604800"))
    store_api_timeout_seconds: float = float(os.getenv("STORE_API_TIMEOUT_SECONDS", "15"))


settings = Settings()
