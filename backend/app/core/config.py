from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
    max_request_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", str(32 * 1024)))


settings = Settings()
