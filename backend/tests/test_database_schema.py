from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, Numeric, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from backend.app.db import (
    AcquisitionMode,
    Base,
    BenefitType,
    DataSource,
    EligibilityRule,
    EligibilityRuleGroup,
    FundingProduct,
    Organization,
    OrganizationRole,
    OrganizationType,
    ProductBenefit,
    ProductOrganization,
    ProductSource,
    ProductStatus,
    ProductType,
    RuleOperator,
)
from backend.app.financial_catalog.persistence import bundle_from_database
from backend.app.financial_catalog.workflow import apply_preview, preview_catalog

EXPECTED_TABLES = {
    "ai_request_events",
    "organizations",
    "data_sources",
    "funding_products",
    "product_organizations",
    "product_benefits",
    "eligibility_rule_groups",
    "eligibility_rules",
    "product_sources",
}


def test_financial_catalog_metadata_is_complete() -> None:
    configure_mappers()
    assert set(Base.metadata.tables) == EXPECTED_TABLES

    benefits = Base.metadata.tables["product_benefits"]
    assert isinstance(benefits.c.amount_max_krw.type, BigInteger)
    assert isinstance(benefits.c.interest_rate_min_pct.type, Numeric)
    assert benefits.c.interest_rate_min_pct.type.scale == 4
    assert isinstance(benefits.c.guarantee_fee_rate_pct.type, Numeric)

    rules = Base.metadata.tables["eligibility_rules"]
    assert isinstance(rules.c.value.type, JSONB)
    assert "ix_eligibility_rules_value_gin" in {index.name for index in rules.indexes}
    products = Base.metadata.tables["funding_products"]
    assert "ix_funding_products_extra_data_gin" in {index.name for index in products.indexes}

    constraint_names = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
    }
    assert "ck_funding_products_application_date_order" in constraint_names
    assert "ck_product_benefits_amount_order" in constraint_names
    assert "uq_product_sources_product_source_external_id" in constraint_names
    assert "ck_ai_request_events_reserved_cost_nonnegative" in constraint_names


def test_catalog_model_represents_roles_benefits_rules_and_sources() -> None:
    checked_at = datetime(2026, 7, 24, tzinfo=UTC)
    bank = Organization(
        code="kb-bank",
        name="KB국민은행",
        organization_type=OrganizationType.BANK,
    )
    source = DataSource(
        key="kb-official-products",
        name="KB국민은행 개인사업자대출",
        acquisition_mode=AcquisitionMode.CURATED_OFFICIAL_SOURCE,
        base_url="https://obank.kbstar.com/",
        organization=bank,
    )
    product = FundingProduct(
        slug="kb-sample-loan",
        name="검증용 대출",
        product_type=ProductType.BANK_LOAN,
        status=ProductStatus.ACTIVE,
        last_checked_at=checked_at,
        extra_data={"channels": ["스타뱅킹"]},
    )
    product.organization_roles.append(
        ProductOrganization(organization=bank, role=OrganizationRole.LENDER)
    )
    product.benefits.append(ProductBenefit(
        benefit_type=BenefitType.LOAN,
        amount_max_krw=100_000_000,
        interest_rate_min_pct=Decimal("3.2500"),
    ))
    group = EligibilityRuleGroup(position=0, name="기본 자격")
    group.rules.extend([
        EligibilityRule(
            position=0,
            field_key="is_small_business",
            operator=RuleOperator.EQUALS,
            value=True,
            description="소상공인이어야 합니다.",
        ),
        EligibilityRule(
            position=1,
            field_key="region_code",
            operator=RuleOperator.IN,
            value=["KR", "11"],
            description="전국 또는 서울 대상입니다.",
        ),
    ])
    product.eligibility_groups.append(group)
    product.sources.append(ProductSource(
        data_source=source,
        external_id="sample-1",
        title="검증용 공식 안내",
        official_url="https://obank.kbstar.com/sample-1",
        checked_at=checked_at,
        content_hash="a" * 64,
        raw_data={"status": "active"},
    ))

    assert product.organization_roles[0].organization is bank
    assert product.benefits[0].amount_max_krw == 100_000_000
    assert [rule.field_key for rule in product.eligibility_groups[0].rules] == [
        "is_small_business", "region_code",
    ]
    assert product.sources[0].data_source.acquisition_mode == AcquisitionMode.CURATED_OFFICIAL_SOURCE


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL을 지정한 PostgreSQL 통합 테스트에서만 실행합니다.",
)
def test_postgresql_round_trip_and_constraints() -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    checked_at = datetime(2026, 7, 24, tzinfo=UTC)
    try:
        with Session(engine) as session:
            bank = Organization(
                code="integration-kb-bank",
                name="KB국민은행",
                organization_type=OrganizationType.BANK,
            )
            source = DataSource(
                key="integration-kb-source",
                name="KB 공식 상품",
                acquisition_mode=AcquisitionMode.CURATED_OFFICIAL_SOURCE,
                base_url="https://obank.kbstar.com/",
                organization=bank,
            )
            product = FundingProduct(
                slug="integration-kb-loan",
                name="통합 검증 대출",
                product_type=ProductType.BANK_LOAN,
                status=ProductStatus.ACTIVE,
                extra_data={"channels": ["스타뱅킹"]},
            )
            product.organization_roles.append(
                ProductOrganization(organization=bank, role=OrganizationRole.LENDER)
            )
            product.benefits.append(ProductBenefit(
                benefit_type=BenefitType.LOAN,
                amount_min_krw=10_000_000,
                amount_max_krw=100_000_000,
                interest_rate_min_pct=Decimal("3.2500"),
                interest_rate_max_pct=Decimal("5.5000"),
            ))
            group = EligibilityRuleGroup(position=0, name="기본 자격")
            group.rules.append(EligibilityRule(
                position=0,
                field_key="region_code",
                operator=RuleOperator.IN,
                value=["KR", "11"],
                description="전국 또는 서울 대상입니다.",
            ))
            product.eligibility_groups.append(group)
            product.sources.append(ProductSource(
                data_source=source,
                external_id="integration-1",
                title="통합 검증 공식 안내",
                official_url="https://obank.kbstar.com/integration-1",
                checked_at=checked_at,
                raw_data={"status": "active"},
            ))
            session.add(product)
            session.flush()
            session.expire_all()

            stored = session.scalar(select(FundingProduct).where(
                FundingProduct.slug == "integration-kb-loan"
            ))
            assert stored is not None
            assert stored.extra_data == {"channels": ["스타뱅킹"]}
            assert stored.benefits[0].interest_rate_min_pct == Decimal("3.2500")
            assert stored.eligibility_groups[0].rules[0].value == ["KR", "11"]
            session.rollback()

        with Session(engine) as session:
            invalid = FundingProduct(
                slug="invalid-benefit",
                name="잘못된 혜택",
                product_type=ProductType.BANK_LOAN,
            )
            invalid.benefits.append(ProductBenefit(
                benefit_type=BenefitType.LOAN,
                amount_min_krw=100,
                amount_max_krw=10,
            ))
            session.add(invalid)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
    finally:
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL을 지정한 PostgreSQL 통합 테스트에서만 실행합니다.",
)
def test_catalog_preview_apply_is_atomic_and_stale_safe(tmp_path: Path) -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    catalog_root = Path(__file__).resolve().parents[2] / "config/financial_catalog"
    try:
        with Session(engine) as session:
            run_dir = preview_catalog(
                session,
                curated_root=catalog_root,
                output_root=tmp_path,
                source="curated",
                now=datetime(2026, 7, 24, tzinfo=UTC),
            )
            result = apply_preview(session, run_dir)
            session.flush()
            stored = bundle_from_database(session)

            assert result == {"added": 37, "updated": 0, "closed": 0}
            assert len(stored.products) == 37
            assert sum(item.slug.startswith("semas-") for item in stored.products) == 11
            assert sum(
                source.external_id == "mss-2026-448"
                for product in stored.products
                for source in product.sources
            ) == 11
            with pytest.raises(ValueError, match="DB 카탈로그가 변경"):
                apply_preview(session, run_dir)

            second_run_dir = preview_catalog(
                session,
                curated_root=catalog_root,
                output_root=tmp_path,
                source="curated",
                now=datetime(2026, 7, 24, 0, 0, 1, tzinfo=UTC),
            )
            second_result = apply_preview(session, second_run_dir)
            session.flush()

            assert second_result == {"added": 0, "updated": 37, "closed": 0}
            assert len(bundle_from_database(session).products) == 37

            api_item = {
                "pblancId": "PBLN_INTEGRATION_ACTIVE",
                "pblancNm": "[서울] 통합 테스트 소상공인 금융지원",
                "pblancUrl": "https://www.bizinfo.go.kr/integration-active",
                "bsnsSumryCn": "서울 소상공인을 위한 통합 테스트 금융지원입니다.",
                "trgetNm": "소상공인",
                "hashTags": "금융,서울,소상공인",
                "reqstBeginEndDe": "예산 소진시까지",
            }
            api_run_dir = preview_catalog(
                session,
                curated_root=catalog_root,
                output_root=tmp_path,
                source="all",
                bizinfo_items=[api_item],
                now=datetime(2026, 7, 24, 0, 0, 2, tzinfo=UTC),
            )
            api_result = apply_preview(session, api_run_dir)
            assert api_result == {"added": 1, "updated": 37, "closed": 0}

            removal_run_dir = preview_catalog(
                session,
                curated_root=catalog_root,
                output_root=tmp_path,
                source="all",
                bizinfo_items=[],
                now=datetime(2026, 7, 24, 0, 0, 3, tzinfo=UTC),
            )
            removal_diff = json.loads(
                (removal_run_dir / "diff.json").read_text(encoding="utf-8")
            )
            removal_result = apply_preview(session, removal_run_dir)
            stored_after_removal = bundle_from_database(session)
            removed_product = next(
                item for item in stored_after_removal.products
                if item.slug == "bizinfo-pbln-integration-active"
            )

            assert removal_diff["close_candidates"] == [
                "bizinfo-pbln-integration-active"
            ]
            assert removal_result == {"added": 0, "updated": 37, "closed": 1}
            assert removed_product.status == ProductStatus.CLOSED
            assert len(stored_after_removal.products) == 38
            session.rollback()
    finally:
        engine.dispose()
