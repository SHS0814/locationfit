"""Raw-to-interim ingestion with explicit duplicate diagnostics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.clean import coerce_key_types, load_column_map, standardize_columns
from src.data.config import load_datasets_config
from src.data.load import read_folder
from src.utils.paths import CONFIG_DIR, INTERIM_DIR, PROJECT_ROOT


def grain_keys(grain: str) -> list[str]:
    """Return canonical key columns for a configured dataset grain."""
    return {
        "area": ["area_code"],
        "quarter_area": ["quarter", "area_code"],
        "quarter_area_industry": ["quarter", "area_code", "industry_code"],
    }.get(grain, [])


def stable_frame_digest(frame: pd.DataFrame, *, sort_by: list[str]) -> str:
    """Return an order- and dtype-representation-independent content digest."""
    columns = sorted(frame.columns)
    canonical = frame.loc[:, columns].convert_dtypes()
    ordering = sort_by or columns
    canonical = canonical.sort_values(
        ordering,
        kind="mergesort",
        na_position="first",
    ).reset_index(drop=True)
    row_hashes = pd.util.hash_pandas_object(canonical, index=False, categorize=True)
    digest = hashlib.sha256()
    digest.update(json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    digest.update(row_hashes.to_numpy(dtype="uint64").astype(">u8", copy=False).tobytes())
    return digest.hexdigest()


def validate_preserved_interim(
    name: str,
    existing: pd.DataFrame,
    current: pd.DataFrame,
    *,
    keys: list[str],
    start_quarter: str,
    end_quarter: str,
) -> dict[str, str]:
    """Require a protected interim file to match the normalized raw result exactly."""
    missing_existing_keys = [key for key in keys if key not in existing]
    if missing_existing_keys:
        raise ValueError(f"[{name}] 기존 interim 표준 키 누락: {missing_existing_keys}")

    existing_columns = set(existing.columns)
    current_columns = set(current.columns)
    if existing_columns != current_columns:
        missing = sorted(current_columns - existing_columns)
        extra = sorted(existing_columns - current_columns)
        raise ValueError(
            f"[{name}] 기존 interim 컬럼이 현재 raw 적재 결과와 다릅니다: "
            f"missing={missing}, extra={extra}"
        )

    if keys:
        for label, candidate in (("기존 interim", existing), ("현재 raw 적재 결과", current)):
            duplicate_rows = int(candidate.duplicated(keys, keep=False).sum())
            if duplicate_rows:
                raise ValueError(
                    f"[{name}] {label}에 중복 표준 키가 있습니다: rows={duplicate_rows:,}"
                )

    if len(existing) != len(current):
        raise ValueError(
            f"[{name}] 기존 interim 행 수가 현재 raw 적재 결과와 다릅니다: "
            f"existing={len(existing):,}, raw={len(current):,}"
        )

    if "quarter" in existing and not existing.empty:
        existing_quarter = existing["quarter"].astype("string")
        if not existing_quarter.between(start_quarter, end_quarter).all():
            raise ValueError(f"[{name}] 기존 interim에 분석 기간 밖 분기가 있습니다.")

    key_digest = stable_frame_digest(existing.loc[:, keys], sort_by=keys) if keys else ""
    current_key_digest = stable_frame_digest(current.loc[:, keys], sort_by=keys) if keys else ""
    if key_digest != current_key_digest:
        raise ValueError(f"[{name}] 기존 interim 핵심 키 집합이 현재 raw 적재 결과와 다릅니다.")

    content_digest = stable_frame_digest(existing, sort_by=keys)
    current_content_digest = stable_frame_digest(current, sort_by=keys)
    if content_digest != current_content_digest:
        raise ValueError(f"[{name}] 기존 interim 값이 현재 raw 적재 결과와 다릅니다.")
    return {"key_digest": key_digest, "content_digest": content_digest}


def ingest_dataset(
    name: str,
    spec: dict[str, Any],
    *,
    start_quarter: str,
    end_quarter: str,
    column_map: dict[str, str],
    project_root: Path = PROJECT_ROOT,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load, standardize, period-filter and diagnose one raw dataset."""
    raw = read_folder(project_root / spec["folder"])
    source_rows = len(raw)
    frame = coerce_key_types(standardize_columns(raw, column_map))
    if "quarter" in frame:
        valid_quarter = frame["quarter"].str.fullmatch(r"\d{4}[1-4]", na=False)
        in_period = frame["quarter"].between(start_quarter, end_quarter)
        frame = frame.loc[valid_quarter & in_period].copy()
    filtered_rows = len(frame)

    data_columns = [column for column in frame.columns if column != "_source_file"]
    exact_mask = frame.duplicated(data_columns, keep="first")
    exact_removed = int(exact_mask.sum())
    frame = frame.loc[~exact_mask].copy()

    keys = grain_keys(spec.get("grain", ""))
    missing_keys = [key for key in keys if key not in frame]
    if missing_keys:
        raise ValueError(f"[{name}] 표준 키 누락: {missing_keys}")
    key_duplicate_mask = frame.duplicated(keys, keep=False) if keys else pd.Series(False, index=frame.index)
    key_duplicate_rows = int(key_duplicate_mask.sum())
    duplicate_cause = "none"
    if key_duplicate_rows:
        duplicate_rows = frame.loc[key_duplicate_mask]
        if "_source_file" in duplicate_rows:
            source_counts = duplicate_rows.groupby(keys, dropna=False)["_source_file"].nunique()
            duplicate_cause = "overlapping_source_files" if source_counts.gt(1).any() else "detail_columns_or_api_page"
        else:
            duplicate_cause = "detail_columns_or_api_page"

    diagnostics = {
        "dataset": name,
        "source_rows": source_rows,
        "period_filtered_rows": filtered_rows,
        "rows_after_exact_dedup": len(frame),
        "exact_duplicate_rows_removed": exact_removed,
        "key_duplicate_rows": key_duplicate_rows,
        "key_duplicate_cause": duplicate_cause,
        "area_count": int(frame["area_code"].nunique()) if "area_code" in frame else 0,
        "industry_count": int(frame["industry_code"].nunique()) if "industry_code" in frame else 0,
        "quarter_count": int(frame["quarter"].nunique()) if "quarter" in frame else 0,
        "quarter_min": frame["quarter"].min() if "quarter" in frame and not frame.empty else None,
        "quarter_max": frame["quarter"].max() if "quarter" in frame and not frame.empty else None,
    }
    frame = frame.drop(columns=["_source_file"], errors="ignore")
    return frame, diagnostics


def ingest_all(
    *,
    config: dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
    output_dir: Path = INTERIM_DIR,
    preserve_existing: tuple[str, ...] = ("sales",),
) -> pd.DataFrame:
    """Ingest raw datasets while preserving explicitly protected interim files."""
    cfg = config or load_datasets_config()
    column_map = load_column_map(CONFIG_DIR / "column_map.yaml")
    start = str(cfg["analysis_period"]["start_quarter"])
    end = str(cfg["analysis_period"]["end_quarter"])
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for name, spec in cfg["datasets"].items():
        try:
            frame, report = ingest_dataset(
                name,
                spec,
                start_quarter=start,
                end_quarter=end,
                column_map=column_map,
                project_root=project_root,
            )
        except FileNotFoundError:
            if spec["required"]:
                missing_required.append(name)
                print(f"[{name}] 필수 데이터가 없어 interim 저장을 건너뜁니다.")
            else:
                print(f"[{name}] 선택 데이터가 없어 interim 저장을 건너뜁니다.")
            continue
        destination = output_dir / f"{name}.parquet"
        if name in preserve_existing and destination.exists():
            existing = pd.read_parquet(destination)
            keys = grain_keys(spec.get("grain", ""))
            preserved = validate_preserved_interim(
                name,
                existing,
                frame,
                keys=keys,
                start_quarter=start,
                end_quarter=end,
            )
            report["preserved_key_digest"] = preserved["key_digest"]
            report["preserved_content_digest"] = preserved["content_digest"]
            report["write_status"] = "preserved_existing"
        else:
            frame.to_parquet(destination, index=False)
            report["write_status"] = "written"
        diagnostics.append(report)
        print(
            f"[{name}] raw={report['source_rows']:,} filtered={report['period_filtered_rows']:,} "
            f"dedup={report['rows_after_exact_dedup']:,} areas={report['area_count']:,} "
            f"industries={report['industry_count']:,} quarters={report['quarter_count']} "
            f"range={report['quarter_min']}~{report['quarter_max']} "
            f"exact_removed={report['exact_duplicate_rows_removed']:,} "
            f"key_duplicates={report['key_duplicate_rows']:,}({report['key_duplicate_cause']}) "
            f"write_status={report['write_status']}"
        )
    diagnostic_frame = pd.DataFrame(diagnostics)
    diagnostic_frame.to_csv(output_dir / "ingest_diagnostics.csv", index=False, encoding="utf-8-sig")
    if missing_required:
        raise FileNotFoundError(f"필수 raw 데이터셋 누락: {', '.join(missing_required)}")
    return diagnostic_frame
