"""Raw and canonical schema aliases used across ingestion and validation."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "quarter": ("기준_년분기_코드", "기준년분기코드", "STDR_YYQU_CD", "quarter"),
    "area_code": ("상권_코드", "상권코드", "TRDAR_CD", "area_code"),
    "area_name": ("상권_코드_명", "상권코드명", "TRDAR_CD_NM", "area_name"),
    "industry_code": (
        "서비스_업종_코드",
        "서비스업종코드",
        "SVC_INDUTY_CD",
        "industry_code",
    ),
    "industry_name": (
        "서비스_업종_코드_명",
        "서비스업종코드명",
        "SVC_INDUTY_CD_NM",
        "industry_name",
    ),
    "sales_amount": ("당월_매출_금액", "총_추정매출", "THSMON_SELNG_AMT"),
    "store_count": ("전체_점포_수", "유사_업종_점포_수", "점포_수", "SIMILR_INDUTY_STOR_CO"),
    "floating_population": ("총_유동인구_수", "총_생활인구_수", "TOT_FLPOP_CO"),
    "resident_population": ("총_상주인구_수", "TOT_REPOP_CO"),
    "worker_population": ("총_직장_인구_수", "총_직장인구_수", "TOT_WRC_POPLTN_CO"),
}

RAW_KEY_TO_CANONICAL = {
    "기준_년분기_코드": "quarter",
    "상권_코드": "area_code",
    "상권_코드_명": "area_name",
    "서비스_업종_코드": "industry_code",
    "서비스_업종_코드_명": "industry_name",
}


def find_column(columns: Iterable[str], canonical_name: str) -> str | None:
    """Find the first present raw alias for a canonical field."""
    present = {str(column).strip(): str(column) for column in columns}
    for alias in COLUMN_ALIASES.get(canonical_name, (canonical_name,)):
        if alias in present:
            return present[alias]
    return None


def resolve_required_keys(df: pd.DataFrame, required_keys: Iterable[str]) -> list[str]:
    """Resolve configured Korean key names against Korean/API/canonical columns."""
    resolved: list[str] = []
    for raw_key in required_keys:
        canonical = RAW_KEY_TO_CANONICAL.get(raw_key, raw_key)
        found = find_column(df.columns, canonical)
        if found is not None:
            resolved.append(found)
    return resolved
