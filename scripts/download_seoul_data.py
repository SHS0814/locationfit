#!/usr/bin/env python3
"""Download configured Seoul commercial-area datasets with safe defaults."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.config import generate_quarters, load_datasets_config, validate_quarter
from src.data.load import discover_files
from src.data.schema import find_column, resolve_required_keys
from src.data.seoul_api import FetchResult, SeoulAPIClient, SeoulAPIError


def parse_args() -> argparse.Namespace:
    """Parse download command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="모든 설정 데이터셋 처리")
    selection.add_argument("--dataset", help="하나의 데이터셋만 처리")
    parser.add_argument("--quarters", nargs="+", type=int, help="수집할 분기 코드")
    parser.add_argument("--overwrite", action="store_true", help="이 스크립트가 만든 대상 파일 덮어쓰기")
    parser.add_argument("--skip-sales", action="store_true", help="추정매출 데이터셋 건너뛰기")
    parser.add_argument(
        "--debug-api",
        action="store_true",
        help="마스킹된 첫 5행 응답 진단만 수행(파일 저장 안 함)",
    )
    return parser.parse_args()


def target_path(spec: dict[str, Any], quarter: int | None) -> Path:
    """Return a raw CSV path under the configured dataset folder."""
    folder = PROJECT_ROOT / spec["folder"]
    prefix = spec["output_prefix"]
    return folder / (f"{prefix}_{quarter}.csv" if quarter is not None else f"{prefix}.csv")


def meta_path(csv_path: Path) -> Path:
    """Return the metadata path next to a raw CSV."""
    return csv_path.with_suffix(".meta.json")


def prepare_frame(rows: list[dict[str, Any]], spec: dict[str, Any]) -> tuple[pd.DataFrame, int, int]:
    """Create a frame, remove exact duplicates, and count remaining key duplicates."""
    frame = pd.DataFrame(rows)
    if frame.empty and not frame.columns.tolist():
        return frame, 0, 0
    exact_duplicates = int(frame.duplicated(keep="first").sum())
    frame = frame.drop_duplicates(keep="first").copy()
    keys = resolve_required_keys(frame, spec.get("required_keys", []))
    key_duplicates = int(frame.duplicated(keys, keep=False).sum()) if len(keys) == len(spec.get("required_keys", [])) else 0
    return frame, exact_duplicates, key_duplicates


def save_result(
    result: FetchResult,
    spec: dict[str, Any],
    dataset: str,
    quarter: int | None,
    *,
    overwrite: bool,
    api_total_count: int | None = None,
) -> int:
    """Validate and atomically save a fetched result plus non-secret metadata."""
    destination = target_path(spec, quarter)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    if result.total_count == 0 or not result.rows:
        raise SeoulAPIError(f"[{dataset}{':' + str(quarter) if quarter else ''}] API 응답이 비어 있어 저장하지 않습니다.")
    frame, duplicate_count, key_duplicate_count = prepare_frame(result.rows, spec)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(destination)
    metadata = {
        "dataset": dataset,
        "api_service_name": spec["api_service_name"],
        "quarter": quarter,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(frame),
        "total_count_from_api": api_total_count if api_total_count is not None else result.total_count,
        "page_size": result.total_count if result.page_count == 1 and result.total_count < 1000 else 1000,
        "source": "Seoul Open Data API",
        "duplicate_row_count": duplicate_count,
        "key_duplicate_row_count": key_duplicate_count,
    }
    meta_path(destination).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(frame)


def split_local_result(
    result: FetchResult,
    spec: dict[str, Any],
    dataset: str,
    quarters: list[int],
    overwrite: bool,
) -> tuple[list[str], list[str]]:
    """Filter a whole-service response locally and save requested quarter files."""
    frame = pd.DataFrame(result.rows)
    quarter_column = find_column(frame.columns, "quarter")
    if quarter_column is None:
        raise SeoulAPIError(f"[{dataset}] 전체 응답에 기준_년분기_코드/STDR_YYQU_CD가 없습니다.")
    numeric_quarter = pd.to_numeric(frame[quarter_column], errors="coerce")
    missing = [quarter for quarter in quarters if not numeric_quarter.eq(quarter).any()]
    if missing:
        raise SeoulAPIError(f"[{dataset}] API 전체 응답에 요청 분기가 없습니다: {missing}")
    saved: list[str] = []
    skipped: list[str] = []
    for quarter in quarters:
        destination = target_path(spec, quarter)
        label = f"{dataset}:{quarter}"
        if destination.exists() and not overwrite:
            skipped.append(label)
            continue
        rows = select_quarter_rows(frame, quarter)
        quarter_result = FetchResult(rows=rows, total_count=len(rows), page_count=result.page_count)
        count = save_result(
            quarter_result,
            spec,
            dataset,
            quarter,
            overwrite=overwrite,
            api_total_count=result.total_count,
        )
        saved.append(f"{label}({count:,})")
    return saved, skipped


def select_quarter_rows(frame: pd.DataFrame, quarter: int) -> list[dict[str, Any]]:
    """Select one quarter from Korean, API or canonical quarter columns."""
    quarter_column = find_column(frame.columns, "quarter")
    if quarter_column is None:
        raise SeoulAPIError("기준_년분기_코드/STDR_YYQU_CD 컬럼이 없습니다.")
    numeric_quarter = pd.to_numeric(frame[quarter_column], errors="coerce")
    return frame.loc[numeric_quarter.eq(quarter)].to_dict("records")


def create_client(config: dict[str, Any], *, debug: bool = False) -> SeoulAPIClient:
    """Create an API client from config without logging credentials."""
    api = config.get("api", {})
    return SeoulAPIClient(
        base_url=api.get("base_url", "http://openapi.seoul.go.kr:8088"),
        page_size=int(api.get("page_size", 1000)),
        timeout=float(api.get("timeout_seconds", 30)),
        max_retries=int(api.get("max_retries", 3)),
        retry_wait=float(api.get("retry_wait_seconds", 1)),
        debug=debug,
    )


def main() -> int:
    """Run selected downloads and return 1 if any required dataset fails."""
    args = parse_args()
    config = load_datasets_config()
    datasets: dict[str, dict[str, Any]] = config["datasets"]
    if args.dataset and args.dataset not in datasets:
        print(f"알 수 없는 데이터셋: {args.dataset}", file=sys.stderr)
        return 2
    default_quarters = generate_quarters(
        config["analysis_period"]["start_quarter"], config["analysis_period"]["end_quarter"]
    )
    quarters = [validate_quarter(value) for value in args.quarters] if args.quarters else default_quarters
    outside = sorted(set(quarters) - set(default_quarters))
    if outside:
        print(f"분석 범위 밖 분기입니다: {outside}", file=sys.stderr)
        return 2

    names = list(datasets) if args.all else [args.dataset]
    succeeded: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    client: SeoulAPIClient | None = None

    for name in names:
        assert name is not None
        spec = datasets[name]
        if name == "sales" and (args.skip_sales or args.all):
            existing = discover_files(PROJECT_ROOT / spec["folder"])
            skipped.append(f"sales(기존 {len(existing)} files; 검증 대상)")
            continue
        if name == "sales" and not args.overwrite:
            existing = discover_files(PROJECT_ROOT / spec["folder"])
            skipped.append(f"sales(재다운로드는 --dataset sales --overwrite만 허용; 기존 {len(existing)} files)")
            continue
        if not spec.get("download_enabled", False) and name != "sales":
            skipped.append(f"{name}(download_enabled=false)")
            continue
        service = spec.get("api_service_name")
        if not service:
            message = f"{name}: api_service_name이 비어 있음(TODO: {spec.get('dataset_id')})"
            failed.append(message)
            print(f"[FAIL] {message}", file=sys.stderr)
            continue
        try:
            if client is None:
                client = create_client(config, debug=args.debug_api)
            mode = spec.get("quarter_filter", {}).get("mode", "local")
            if args.debug_api:
                if not spec.get("quarterly", True):
                    client.fetch_page(service, label=name)
                    succeeded.append(f"{name}(debug only)")
                elif mode == "path":
                    for quarter in quarters:
                        client.fetch_page(
                            service,
                            path_filters=(quarter,),
                            label=f"{name}:{quarter}",
                        )
                        succeeded.append(f"{name}:{quarter}(debug only)")
                elif mode == "local":
                    client.fetch_page(service, label=f"{name}:all")
                    succeeded.append(f"{name}:all(debug only; local filter)")
                else:
                    raise ValueError(f"[{name}] 지원하지 않는 quarter_filter.mode: {mode}")
                continue
            if not spec.get("quarterly", True):
                destination = target_path(spec, None)
                if destination.exists() and not args.overwrite:
                    skipped.append(name)
                    continue
                result = client.fetch_all(service, label=name)
                count = save_result(result, spec, name, None, overwrite=args.overwrite)
                succeeded.append(f"{name}({count:,})")
            elif mode == "path":
                for quarter in quarters:
                    destination = target_path(spec, quarter)
                    label = f"{name}:{quarter}"
                    if destination.exists() and not args.overwrite:
                        skipped.append(label)
                        continue
                    result = client.fetch_all(service, path_filters=(quarter,), label=label)
                    count = save_result(result, spec, name, quarter, overwrite=args.overwrite)
                    succeeded.append(f"{label}({count:,})")
            elif mode == "local":
                needed = [q for q in quarters if args.overwrite or not target_path(spec, q).exists()]
                if not needed:
                    skipped.append(f"{name}(모든 분기 존재)")
                    continue
                skipped.extend(f"{name}:{q}" for q in quarters if q not in needed)
                result = client.fetch_all(service, label=f"{name}:all")
                saved, local_skipped = split_local_result(result, spec, name, needed, args.overwrite)
                succeeded.extend(saved)
                skipped.extend(local_skipped)
            else:
                raise ValueError(f"[{name}] 지원하지 않는 quarter_filter.mode: {mode}")
        except (OSError, ValueError, SeoulAPIError, pd.errors.ParserError) as exc:
            message = f"{name}: {exc}"
            failed.append(message)
            print(f"[FAIL] {message}", file=sys.stderr)

    print("\n=== 수집 요약 ===")
    print("성공:", ", ".join(succeeded) if succeeded else "-")
    print("건너뜀:", ", ".join(skipped) if skipped else "-")
    print("실패:", ", ".join(failed) if failed else "-")
    required_failed = any(item.split(":", 1)[0] in datasets and datasets[item.split(":", 1)[0]]["required"] for item in failed)
    return 1 if required_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
