#!/usr/bin/env python3
"""Generate historical schema, code overlap and distribution reports."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.historical import check_historical_compatibility


def main() -> int:
    """Run historical checks and print a compact report summary."""
    reports = check_historical_compatibility()
    for name, report in reports.items():
        print(f"{name:28} {len(report):8,} rows")
    warnings = []
    for report in reports.values():
        if "warning" in report:
            warning_values = report["warning"].fillna("").astype(str)
            warnings.extend(warning_values[warning_values.ne("")].tolist())
    if warnings:
        print(f"검토 경고 {len(warnings)}건: 기준 변경으로 단정하지 말고 원본 명세를 확인하세요.")
    print("보고서: outputs/tables/historical_schema_changes.csv 외 3개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
