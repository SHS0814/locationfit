"""Configuration and quarter helpers for the data pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.utils.paths import CONFIG_DIR


def validate_quarter(quarter: int | str) -> int:
    """Return a validated YYYYQ-style Seoul quarter code (for example 20211)."""
    value = int(quarter)
    year, number = divmod(value, 10)
    if year < 1900 or number not in {1, 2, 3, 4}:
        raise ValueError(f"잘못된 분기 코드입니다: {quarter} (마지막 자리는 1~4)")
    return value


def generate_quarters(start_quarter: int | str, end_quarter: int | str) -> list[int]:
    """Generate inclusive quarter codes between two validated endpoints."""
    start = validate_quarter(start_quarter)
    end = validate_quarter(end_quarter)
    if start > end:
        raise ValueError(f"시작 분기({start})가 종료 분기({end})보다 늦습니다.")
    result: list[int] = []
    current = start
    while current <= end:
        result.append(current)
        year, number = divmod(current, 10)
        current = (year + 1) * 10 + 1 if number == 4 else current + 1
    return result


def load_datasets_config(path: Path | None = None) -> dict[str, Any]:
    """Load and minimally validate the datasets YAML configuration."""
    config_path = path or CONFIG_DIR / "datasets.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if "analysis_period" not in config or "datasets" not in config:
        raise ValueError(f"필수 설정이 없습니다: {config_path}")
    period = config["analysis_period"]
    generate_quarters(period["start_quarter"], period["end_quarter"])
    return config
