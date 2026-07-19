#!/usr/bin/env python3
"""Validate all configured raw datasets and save inventory reports."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.reporting import required_failures, validate_raw_datasets


def main() -> int:
    """Print dataset totals and return 1 when required raw data is invalid."""
    reports = validate_raw_datasets()
    totals = reports["inventory"][reports["inventory"]["file"].eq("__TOTAL__")]
    columns = [
        "dataset",
        "status",
        "row_count",
        "area_count",
        "industry_count",
        "quarter_min",
        "quarter_max",
        "missing_quarters",
    ]
    print(totals[columns].fillna("").to_string(index=False))
    print("\n보고서: outputs/tables/raw_*_report.csv, quarter_coverage_report.csv")
    failures = required_failures(reports)
    if not failures.empty:
        print("\n필수 데이터셋 누락/오류:", ", ".join(failures["dataset"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
