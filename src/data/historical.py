"""Historical schema, code-system and value-distribution compatibility checks."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Any

import pandas as pd

from src.data.clean import coerce_key_types, load_column_map, standardize_columns
from src.data.config import load_datasets_config
from src.data.load import discover_files, read_table
from src.data.schema import find_column
from src.utils.paths import CONFIG_DIR, OUTPUT_DIR, PROJECT_ROOT


def _year_series(frame: pd.DataFrame, path: Path) -> pd.Series:
    if "quarter" in frame:
        years = pd.to_numeric(frame["quarter"], errors="coerce").floordiv(10).astype("Int64")
        if years.notna().any():
            return years
    match = re.search(r"(20\d{2})", path.name)
    fallback = int(match.group(1)) if match else pd.NA
    return pd.Series([fallback] * len(frame), index=frame.index, dtype="Int64")


def _rename_candidate(removed: str, added: set[str]) -> tuple[str | None, float]:
    if not added:
        return None, 0.0
    scores = [(name, SequenceMatcher(None, removed.replace("_", ""), name.replace("_", "")).ratio()) for name in added]
    name, score = max(scores, key=lambda item: item[1])
    return (name, score) if score >= 0.65 else (None, score)


def check_historical_compatibility(
    *,
    config: dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
    save: bool = True,
) -> dict[str, pd.DataFrame]:
    """Compare annual schemas, area/industry codes and numeric distributions."""
    cfg = config or load_datasets_config()
    column_map = load_column_map(CONFIG_DIR / "column_map.yaml")
    schemas: dict[str, dict[int, dict[str, set[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    area_codes: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    area_names: dict[str, dict[int, dict[str, set[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    industry_codes: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    industry_names: dict[str, dict[int, dict[str, set[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    distribution_parts: dict[tuple[str, int, str], list[pd.Series]] = defaultdict(list)
    metric_by_dataset = {
        "sales": "sales_amount",
        "stores": "store_count",
        "floating_population": "floating_population",
        "resident_population": "resident_population",
        "worker_population": "worker_population",
    }

    for dataset, spec in cfg["datasets"].items():
        for path in discover_files(project_root / spec["folder"]):
            raw = read_table(path)
            frame = coerce_key_types(standardize_columns(raw, column_map))
            years = _year_series(frame, path)
            for year_value in sorted(years.dropna().unique()):
                year = int(year_value)
                mask = years.eq(year).fillna(False)
                annual = frame.loc[mask]
                for column in raw.columns:
                    schemas[dataset][year][str(column)].add(str(raw[column].dtype))
                if "area_code" in annual:
                    area_codes[dataset][year].update(annual["area_code"].dropna().astype(str))
                    if "area_name" in annual:
                        pairs = annual[["area_code", "area_name"]].dropna().drop_duplicates()
                        for code, name in pairs.itertuples(index=False):
                            area_names[dataset][year][str(code)].add(str(name))
                if "industry_code" in annual:
                    industry_codes[dataset][year].update(annual["industry_code"].dropna().astype(str))
                    if "industry_name" in annual:
                        pairs = annual[["industry_code", "industry_name"]].dropna().drop_duplicates()
                        for code, name in pairs.itertuples(index=False):
                            industry_names[dataset][year][str(code)].add(str(name))
                metric = metric_by_dataset.get(dataset)
                if metric:
                    raw_metric = find_column(raw.columns, metric)
                    if raw_metric is not None:
                        values = pd.to_numeric(raw.loc[mask, raw_metric], errors="coerce").dropna()
                        if not values.empty:
                            distribution_parts[(dataset, year, metric)].append(values)

    schema_rows: list[dict[str, Any]] = []
    for dataset, annual_schemas in schemas.items():
        years = sorted(annual_schemas)
        for previous, current in zip(years, years[1:]):
            old = set(annual_schemas[previous])
            new = set(annual_schemas[current])
            added = new - old
            removed = old - new
            for column in sorted(added):
                schema_rows.append(
                    {"dataset": dataset, "from_year": previous, "to_year": current, "change_type": "added", "column": column}
                )
            for column in sorted(removed):
                candidate, score = _rename_candidate(column, added)
                schema_rows.append(
                    {
                        "dataset": dataset,
                        "from_year": previous,
                        "to_year": current,
                        "change_type": "removed",
                        "column": column,
                        "possible_rename": candidate,
                        "rename_similarity": score,
                    }
                )
            for column in sorted(old & new):
                before = "|".join(sorted(annual_schemas[previous][column]))
                after = "|".join(sorted(annual_schemas[current][column]))
                if before != after:
                    schema_rows.append(
                        {
                            "dataset": dataset,
                            "from_year": previous,
                            "to_year": current,
                            "change_type": "dtype_changed",
                            "column": column,
                            "before_dtype": before,
                            "after_dtype": after,
                        }
                    )

    area_rows: list[dict[str, Any]] = []
    for dataset, annual_codes in area_codes.items():
        years = sorted(annual_codes)
        for year in years:
            area_rows.append(
                {"dataset": dataset, "from_year": year, "to_year": year, "comparison": "year_count", "from_count": len(annual_codes[year])}
            )
        for previous, current in zip(years, years[1:]):
            old, new = annual_codes[previous], annual_codes[current]
            intersection = old & new
            changed_names = sum(
                bool(area_names[dataset][previous].get(code) - area_names[dataset][current].get(code, set()))
                for code in intersection
            )
            changed_name_codes = sorted(
                code
                for code in intersection
                if area_names[dataset][previous].get(code) != area_names[dataset][current].get(code)
            )
            retention = len(intersection) / len(old) if old else None
            area_rows.append(
                {
                    "dataset": dataset,
                    "from_year": previous,
                    "to_year": current,
                    "comparison": "year_overlap",
                    "from_count": len(old),
                    "to_count": len(new),
                    "intersection_count": len(intersection),
                    "retention_rate": retention,
                    "added_count": len(new - old),
                    "removed_count": len(old - new),
                    "added_codes": "|".join(sorted(new - old)),
                    "removed_codes": "|".join(sorted(old - new)),
                    "area_name_changed_count": changed_names,
                    "area_name_changed_codes": "|".join(changed_name_codes),
                    "warning": "REVIEW_LARGE_CODE_CHANGE" if retention is not None and retention < 0.9 else "",
                }
            )

    industry_rows: list[dict[str, Any]] = []
    for dataset, annual_codes in industry_codes.items():
        years = sorted(annual_codes)
        for previous, current in zip(years, years[1:]):
            old, new = annual_codes[previous], annual_codes[current]
            intersection = old & new
            changed_names = sum(
                bool(industry_names[dataset][previous].get(code) - industry_names[dataset][current].get(code, set()))
                for code in intersection
            )
            changed_name_codes = sorted(
                code
                for code in intersection
                if industry_names[dataset][previous].get(code) != industry_names[dataset][current].get(code)
            )
            industry_rows.append(
                {
                    "comparison": "year_overlap",
                    "dataset_left": dataset,
                    "dataset_right": dataset,
                    "year": current,
                    "left_count": len(old),
                    "right_count": len(new),
                    "intersection_count": len(intersection),
                    "overlap_rate_left": len(intersection) / len(old) if old else None,
                    "added_count": len(new - old),
                    "removed_count": len(old - new),
                    "added_codes": "|".join(sorted(new - old)),
                    "removed_codes": "|".join(sorted(old - new)),
                    "industry_name_changed_count": changed_names,
                    "industry_name_changed_codes": "|".join(changed_name_codes),
                }
            )
    common_years = sorted(set(industry_codes.get("sales", {})) & set(industry_codes.get("stores", {})))
    for year in common_years:
        sales_codes = industry_codes["sales"][year]
        store_codes = industry_codes["stores"][year]
        intersection = sales_codes & store_codes
        industry_rows.append(
            {
                "comparison": "sales_stores",
                "dataset_left": "sales",
                "dataset_right": "stores",
                "year": year,
                "left_count": len(sales_codes),
                "right_count": len(store_codes),
                "intersection_count": len(intersection),
                "overlap_rate_left": len(intersection) / len(sales_codes) if sales_codes else None,
                "overlap_rate_right": len(intersection) / len(store_codes) if store_codes else None,
                "left_only_codes": "|".join(sorted(sales_codes - store_codes)),
                "right_only_codes": "|".join(sorted(store_codes - sales_codes)),
            }
        )

    distribution_rows: list[dict[str, Any]] = []
    medians: dict[tuple[str, str], tuple[int, float]] = {}
    for (dataset, year, metric), parts in sorted(distribution_parts.items()):
        values = pd.concat(parts, ignore_index=True)
        median = float(values.median())
        warning = ""
        prior = medians.get((dataset, metric))
        ratio: float | None = None
        if prior and prior[1] != 0:
            ratio = median / prior[1]
            if ratio > 2 or ratio < 0.5:
                warning = "REVIEW_SIMULTANEOUS_DISTRIBUTION_SHIFT"
        medians[(dataset, metric)] = (year, median)
        distribution_rows.append(
            {
                "dataset": dataset,
                "year": year,
                "metric": metric,
                "count": int(values.count()),
                "median": median,
                "mean": float(values.mean()),
                "p05": float(values.quantile(0.05)),
                "p95": float(values.quantile(0.95)),
                "median_ratio_vs_previous": ratio,
                "warning": warning,
                "interpretation": "기준 변경 단정 금지; 원본 명세 검토 필요" if warning else "",
            }
        )

    reports = {
        "schema_changes": pd.DataFrame(
            schema_rows,
            columns=[
                "dataset", "from_year", "to_year", "change_type", "column",
                "possible_rename", "rename_similarity", "before_dtype", "after_dtype",
            ],
        ),
        "area_code_overlap": pd.DataFrame(area_rows),
        "industry_code_overlap": pd.DataFrame(industry_rows),
        "yearly_distribution": pd.DataFrame(distribution_rows),
    }
    if save:
        output = OUTPUT_DIR / "tables"
        output.mkdir(parents=True, exist_ok=True)
        filenames = {
            "schema_changes": "historical_schema_changes.csv",
            "area_code_overlap": "area_code_overlap.csv",
            "industry_code_overlap": "industry_code_overlap.csv",
            "yearly_distribution": "yearly_distribution_report.csv",
        }
        for key, filename in filenames.items():
            reports[key].to_csv(output / filename, index=False, encoding="utf-8-sig")
    return reports
