from __future__ import annotations

import pandas as pd


def coverage_report(df: pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {"rows": len(df), "columns": len(df.columns)}
    if "quarter" in df.columns:
        out.update(quarter_min=df["quarter"].min(), quarter_max=df["quarter"].max(), quarter_count=df["quarter"].nunique())
    if "area_code" in df.columns:
        out["area_count"] = df["area_code"].nunique()
    if "industry_code" in df.columns:
        out["industry_count"] = df["industry_code"].nunique()
    return out
