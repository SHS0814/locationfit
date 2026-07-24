#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.core.config import PROJECT_ROOT, settings
from backend.app.db.session import session_scope
from backend.app.financial_catalog.persistence import bundle_from_database
from backend.app.financial_catalog.validation import validate_catalog
from backend.app.financial_catalog.workflow import apply_preview, preview_catalog


DEFAULT_CURATED_ROOT = PROJECT_ROOT / "config/financial_catalog"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs/financial_catalog"


def main() -> None:
    parser = argparse.ArgumentParser(description="금융지원 상품 카탈로그 수집·검수·반영")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser("preview", help="DB 변경 없이 수집 결과와 diff를 생성")
    preview.add_argument("--source", choices=("curated", "bizinfo", "all"), required=True)
    preview.add_argument("--curated-root", type=Path, default=DEFAULT_CURATED_ROOT)
    preview.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    apply = subparsers.add_parser("apply", help="검증된 preview를 트랜잭션으로 반영")
    apply.add_argument("--run-dir", type=Path, required=True)
    apply.add_argument("--accept-warnings", action="store_true")

    subparsers.add_parser("validate", help="현재 DB 카탈로그 품질을 검증")
    args = parser.parse_args()

    with session_scope() as session:
        if args.command == "preview":
            run_dir = preview_catalog(
                session,
                curated_root=args.curated_root,
                output_root=args.output_root,
                source=args.source,
                bizinfo_api_key=settings.bizinfo_api_key,
            )
            print(f"preview 완료: {run_dir}")
        elif args.command == "apply":
            result = apply_preview(
                session,
                args.run_dir.resolve(),
                accept_warnings=args.accept_warnings,
            )
            print(
                "apply 완료: "
                f"added={result['added']}, updated={result['updated']}, closed={result['closed']}"
            )
        else:
            report = validate_catalog(bundle_from_database(session))
            print(
                f"검증 완료: products={report.product_count}, errors={report.error_count}, "
                f"warnings={report.warning_count}"
            )
            for issue in report.issues:
                print(f"[{issue.severity}] {issue.code}: {issue.location or '-'}: {issue.message}")
            if report.error_count:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
