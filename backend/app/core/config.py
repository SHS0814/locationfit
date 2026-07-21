from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "KB 상권추천 API")
    app_env: str = os.getenv("APP_ENV", "development")
    api_prefix: str = "/api/v1"
    artifact_dir: Path = Path(
        os.getenv("ARTIFACT_DIR", str(PROJECT_ROOT / "backend/artifacts/current"))
    ).resolve()
    cors_origins: tuple[str, ...] = _csv_env(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    agent_rate_limit_per_minute: int = int(os.getenv("AGENT_RATE_LIMIT_PER_MINUTE", "10"))
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    agent_timeout_seconds: float = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
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
