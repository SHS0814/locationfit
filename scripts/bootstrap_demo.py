#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from alembic import command
from alembic.config import Config

from backend.app.db.session import session_scope
from backend.app.financial_catalog.loader import load_curated_catalog
from backend.app.financial_catalog.persistence import apply_bundle, bundle_from_database
from backend.app.financial_catalog.validation import validate_catalog

CATALOG_ROOT = REPOSITORY_ROOT / "config/financial_catalog"


def migrate_database() -> None:
    config = Config(str(REPOSITORY_ROOT / "backend/alembic.ini"))
    command.upgrade(config, "head")


def seed_curated_catalog() -> None:
    bundle = load_curated_catalog(CATALOG_ROOT)
    checked_at = max(
        (
            source.checked_at
            for product in bundle.products
            for source in product.sources
        ),
        default=datetime.now(UTC),
    )
    report = validate_catalog(bundle, now=checked_at)
    if report.error_count:
        details = "; ".join(
            f"{issue.code}: {issue.message}"
            for issue in report.issues
            if issue.severity == "error"
        )
        raise RuntimeError(f"검수 카탈로그에 오류가 있어 초기화할 수 없습니다: {details}")

    with session_scope() as session:
        current = bundle_from_database(session)
        if current.products:
            print(f"금융지원 카탈로그 유지: 기존 상품 {len(current.products)}개")
            return
        result = apply_bundle(session, bundle)
        print(f"금융지원 카탈로그 초기화: 상품 {result['added']}개")


def main() -> None:
    migrate_database()
    seed_curated_catalog()
    print("데모 DB 준비 완료")


if __name__ == "__main__":
    main()
