"""Raw data inventory and validation reports shared by scripts and notebooks."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.clean import coerce_key_types, load_column_map, standardize_columns
from src.data.config import generate_quarters, load_datasets_config
from src.data.load import detect_csv_encoding, discover_files, read_table
from src.data.schema import find_column
from src.utils.paths import CONFIG_DIR, OUTPUT_DIR, PROJECT_ROOT


def _api_error_present(frame: pd.DataFrame) -> bool:
    suspicious_columns = {"RESULT", "RESULT.CODE", "RESULT.MESSAGE", "CODE", "MESSAGE"}
    if suspicious_columns.intersection(map(str, frame.columns)):
        return True
    if frame.empty:
        return False
    sample = frame.head(20).astype("string").fillna("")
    return bool(sample.apply(lambda column: column.str.contains(r"ERROR-\d+|INFO-100", regex=True).any()).any())


def _expected_keys(grain: str) -> list[str]:
    if grain == "quarter_area_industry":
        return ["quarter", "area_code", "industry_code"]
    if grain == "quarter_area":
        return ["quarter", "area_code"]
    if grain == "area":
        return ["area_code"]
    return []


def _safe_min(series: pd.Series) -> Any:
    values = series.dropna()
    return values.min() if not values.empty else None


def _safe_max(series: pd.Series) -> Any:
    values = series.dropna()
    return values.max() if not values.empty else None


def validate_raw_datasets(
    *,
    config: dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
    save: bool = True,
) -> dict[str, pd.DataFrame]:
    """Inspect all configured raw files and return four validation reports."""
    cfg = config or load_datasets_config()
    column_map = load_column_map(CONFIG_DIR / "column_map.yaml")
    expected_quarters = generate_quarters(
        cfg["analysis_period"]["start_quarter"], cfg["analysis_period"]["end_quarter"]
    )
    inventory_rows: list[dict[str, Any]] = []
    schema_rows: list[dict[str, Any]] = []
    duplicate_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for dataset, spec in cfg["datasets"].items():
        folder = project_root / spec["folder"]
        files = discover_files(folder)
        dataset_quarters: Counter[str] = Counter()
        dataset_quarter_areas: dict[str, set[str]] = {}
        dataset_areas: set[str] = set()
        dataset_industries: set[str] = set()
        key_parts: list[pd.DataFrame] = []
        total_rows = 0
        total_exact_duplicates = 0
        total_api_errors = 0
        unreadable_files = 0
        dataset_missing_core: set[str] = set()

        if not files:
            inventory_rows.append(
                {
                    "dataset": dataset,
                    "file": None,
                    "required": spec["required"],
                    "status": "MISSING" if spec["required"] else "OPTIONAL_MISSING",
                    "encoding": None,
                    "row_count": 0,
                    "column_count": 0,
                    "empty": True,
                    "api_error_present": False,
                    "area_count": 0,
                    "industry_count": 0,
                    "quarter_count": 0,
                    "quarter_min": None,
                    "quarter_max": None,
                }
            )

        for path in files:
            encoding: str | None = None
            try:
                if path.suffix.lower() == ".csv":
                    encoding = detect_csv_encoding(path)
                raw = read_table(path)
            except Exception as exc:  # validation must continue and report every file
                unreadable_files += 1
                inventory_rows.append(
                    {
                        "dataset": dataset,
                        "file": path.name,
                        "required": spec["required"],
                        "status": "UNREADABLE",
                        "encoding": encoding,
                        "row_count": None,
                        "column_count": None,
                        "empty": None,
                        "api_error_present": None,
                        "error": str(exc),
                    }
                )
                continue

            frame = coerce_key_types(standardize_columns(raw, column_map))
            row_count = len(frame)
            total_rows += row_count
            exact_duplicates = int(raw.duplicated(keep=False).sum())
            total_exact_duplicates += exact_duplicates
            api_error = _api_error_present(raw)
            total_api_errors += int(api_error)
            quarter_count = int(frame["quarter"].nunique()) if "quarter" in frame else 0
            area_count = int(frame["area_code"].nunique()) if "area_code" in frame else 0
            industry_count = int(frame["industry_code"].nunique()) if "industry_code" in frame else 0
            if "quarter" in frame:
                counts = frame["quarter"].dropna().value_counts()
                dataset_quarters.update({str(key): int(value) for key, value in counts.items()})
                if "area_code" in frame:
                    for quarter, group in frame[["quarter", "area_code"]].dropna().groupby("quarter"):
                        dataset_quarter_areas.setdefault(str(quarter), set()).update(group["area_code"].astype(str))
            if "area_code" in frame:
                dataset_areas.update(frame["area_code"].dropna().astype(str))
            if "industry_code" in frame:
                dataset_industries.update(frame["industry_code"].dropna().astype(str))

            keys = _expected_keys(spec.get("grain", ""))
            present_keys = [key for key in keys if key in frame.columns]
            missing_keys = sorted(set(keys) - set(present_keys))
            required_core = list(keys)
            if spec.get("grain") == "quarter_area_industry":
                required_core.append("industry_name")
            metric_name = {"sales": "sales_amount", "stores": "store_count"}.get(dataset)
            missing_core = [column for column in required_core if column not in frame.columns]
            if metric_name and find_column(raw.columns, metric_name) is None:
                missing_core.append(metric_name)
            dataset_missing_core.update(missing_core)
            key_duplicate_count = (
                int(frame.duplicated(present_keys, keep=False).sum()) if present_keys and not missing_keys else None
            )
            if present_keys and not missing_keys:
                part = frame[present_keys].copy()
                part["_source_file"] = path.name
                key_parts.append(part)

            inventory_rows.append(
                {
                    "dataset": dataset,
                    "file": path.name,
                    "required": spec["required"],
                    "status": "EMPTY" if raw.empty else ("API_ERROR" if api_error else "OK"),
                    "encoding": encoding or path.suffix.lower().lstrip("."),
                    "row_count": row_count,
                    "column_count": len(raw.columns),
                    "empty": raw.empty,
                    "api_error_present": api_error,
                    "area_count": area_count,
                    "industry_count": industry_count,
                    "quarter_count": quarter_count,
                    "quarter_min": _safe_min(frame["quarter"]) if "quarter" in frame else None,
                    "quarter_max": _safe_max(frame["quarter"]) if "quarter" in frame else None,
                    "missing_required_keys": "|".join(missing_keys),
                    "missing_core_columns": "|".join(missing_core),
                }
            )
            duplicate_rows.append(
                {
                    "dataset": dataset,
                    "file": path.name,
                    "scope": "file",
                    "row_count": row_count,
                    "exact_duplicate_rows": exact_duplicates,
                    "key_columns": "|".join(present_keys),
                    "key_duplicate_rows": key_duplicate_count,
                }
            )
            for column in raw.columns:
                schema_rows.append(
                    {
                        "dataset": dataset,
                        "file": path.name,
                        "column": column,
                        "dtype": str(raw[column].dtype),
                        "missing_count": int(raw[column].isna().sum()),
                        "missing_rate": float(raw[column].isna().mean()) if row_count else None,
                    }
                )

        keys = _expected_keys(spec.get("grain", ""))
        dataset_key_duplicates: int | None = None
        cross_file_key_duplicates: int | None = None
        if key_parts:
            combined_keys = pd.concat(key_parts, ignore_index=True)
            dataset_key_duplicates = int(combined_keys.duplicated(keys, keep=False).sum())
            duplicate_mask = combined_keys.duplicated(keys, keep=False)
            if duplicate_mask.any():
                grouped_sources = combined_keys.loc[duplicate_mask].groupby(keys, dropna=False)["_source_file"].nunique()
                cross_keys = grouped_sources[grouped_sources.gt(1)].index
                if len(keys) == 1:
                    cross_file_key_duplicates = int(combined_keys[keys[0]].isin(list(cross_keys)).sum())
                else:
                    cross_index = pd.MultiIndex.from_tuples(list(cross_keys), names=keys)
                    row_index = pd.MultiIndex.from_frame(combined_keys[keys])
                    cross_file_key_duplicates = int(row_index.isin(cross_index).sum())
            else:
                cross_file_key_duplicates = 0

        duplicate_rows.append(
            {
                "dataset": dataset,
                "file": None,
                "scope": "dataset",
                "row_count": total_rows,
                "exact_duplicate_rows": total_exact_duplicates,
                "key_columns": "|".join(keys),
                "key_duplicate_rows": dataset_key_duplicates,
                "cross_file_key_duplicate_rows": cross_file_key_duplicates,
            }
        )

        if spec.get("quarterly", True):
            for quarter in expected_quarters:
                value = dataset_quarters.get(str(quarter), 0)
                coverage_rows.append(
                    {
                        "dataset": dataset,
                        "quarter": str(quarter),
                        "expected": True,
                        "present": value > 0,
                        "row_count": value,
                        "area_count": len(dataset_quarter_areas.get(str(quarter), set())),
                    }
                )
            for quarter, count in sorted(dataset_quarters.items()):
                if quarter not in {str(value) for value in expected_quarters}:
                    coverage_rows.append(
                        {
                            "dataset": dataset,
                            "quarter": quarter,
                            "expected": False,
                            "present": True,
                            "row_count": count,
                            "area_count": len(dataset_quarter_areas.get(quarter, set())),
                        }
                    )
        inventory_rows.append(
            {
                "dataset": dataset,
                "file": "__TOTAL__",
                "required": spec["required"],
                "file_count": len(files),
                "status": (
                    "MISSING"
                    if not files or not total_rows
                    else "UNREADABLE"
                    if unreadable_files
                    else "API_ERROR"
                    if total_api_errors
                    else "SCHEMA_ERROR"
                    if dataset_missing_core
                    else "KEY_DUPLICATES"
                    if dataset_key_duplicates
                    else "OK"
                ),
                "encoding": None,
                "row_count": total_rows,
                "column_count": None,
                "empty": total_rows == 0,
                "api_error_present": bool(total_api_errors),
                "area_count": len(dataset_areas),
                "industry_count": len(dataset_industries),
                "quarter_count": len(dataset_quarters),
                "quarter_min": min(dataset_quarters) if dataset_quarters else None,
                "quarter_max": max(dataset_quarters) if dataset_quarters else None,
                "missing_quarters": "|".join(
                    str(q) for q in expected_quarters if str(q) not in dataset_quarters
                )
                if spec.get("quarterly", True)
                else "",
                "missing_core_columns": "|".join(sorted(dataset_missing_core)),
            }
        )

    reports = {
        "inventory": pd.DataFrame(inventory_rows),
        "schema": pd.DataFrame(schema_rows),
        "duplicates": pd.DataFrame(duplicate_rows),
        "quarter_coverage": pd.DataFrame(coverage_rows),
    }
    if save:
        output = OUTPUT_DIR / "tables"
        output.mkdir(parents=True, exist_ok=True)
        reports["inventory"].to_csv(output / "raw_data_inventory.csv", index=False, encoding="utf-8-sig")
        reports["schema"].to_csv(output / "raw_schema_report.csv", index=False, encoding="utf-8-sig")
        reports["duplicates"].to_csv(output / "raw_duplicate_report.csv", index=False, encoding="utf-8-sig")
        reports["quarter_coverage"].to_csv(
            output / "quarter_coverage_report.csv", index=False, encoding="utf-8-sig"
        )
    return reports


def required_failures(reports: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return required dataset total rows that are missing, unreadable or API errors."""
    inventory = reports["inventory"]
    totals = inventory[inventory["file"].eq("__TOTAL__") & inventory["required"].eq(True)].copy()
    return totals[
        totals["status"].ne("OK") | totals["empty"].eq(True) | totals["api_error_present"].eq(True)
    ]
