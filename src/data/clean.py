from __future__ import annotations
import re
import pandas as pd
import yaml
from pathlib import Path

def normalize_column_name(name: str) -> str:
    """Normalize whitespace in a source column name."""
    return re.sub(r"\s+", "_", str(name).strip())

def load_column_map(path: Path) -> dict[str, str]:
    """Load raw-to-canonical column aliases."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def standardize_columns(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """Rename configured Korean and API columns without changing source values."""
    result = df.copy()
    result.columns = [normalize_column_name(c) for c in result.columns]
    normalized_map = {normalize_column_name(k): v for k, v in column_map.items()}
    return result.rename(columns=normalized_map)

def coerce_key_types(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce canonical keys to trimmed strings and remove spreadsheet .0 suffixes."""
    result = df.copy()
    for column in ("quarter", "area_code", "industry_code"):
        if column in result.columns:
            result[column] = result[column].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return result
