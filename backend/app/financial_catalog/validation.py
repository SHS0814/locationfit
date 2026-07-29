from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from backend.app.db.models import AcquisitionMode, OrganizationRole, ProductStatus
from backend.app.financial_catalog.contracts import (
    CatalogBundle,
    ValidationIssue,
    ValidationReport,
)


KNOWN_RULE_FIELDS = {
    "region_code",
    "business_status",
    "business_age_months",
    "is_small_business",
    "business_entity_type",
    "industry_code",
    "annual_revenue_krw",
    "recent_sales_months",
    "credit_score_nice",
    "credit_score_kcb",
    "vulnerability_category",
    "has_miso_good_repayment_history",
    "online_seller",
}
ALLOWED_EXTRA_KEYS = {
    "funding_purposes",
    "rate_basis",
    "repayment_methods",
    "application_channels",
    "closing_condition",
    "contact",
    "category",
    "eligibility_notes",
    "curation_level",
    "application_period_text",
    "target_text",
}


def validate_catalog(
    bundle: CatalogBundle,
    *,
    now: datetime | None = None,
) -> ValidationReport:
    checked_at = now or datetime.now(UTC)
    issues: list[ValidationIssue] = []
    organizations = {item.code for item in bundle.organizations}
    sources = {item.key: item for item in bundle.data_sources}
    products = {item.slug for item in bundle.products}
    source_counts: Counter[str] = Counter()
    products_with_amount = 0
    products_with_rate = 0
    structured_rule_count = 0

    for source in bundle.data_sources:
        if source.organization_code and source.organization_code not in organizations:
            issues.append(ValidationIssue(
                severity="error", code="unknown_source_organization",
                message=f"출처 기관 코드가 없습니다: {source.organization_code}",
                location=f"data_sources.{source.key}",
            ))

    for alias in bundle.source_aliases:
        if alias.data_source_key not in sources:
            issues.append(ValidationIssue(
                severity="error", code="unknown_alias_source",
                message=f"별칭 출처 키가 없습니다: {alias.data_source_key}",
            ))
        for slug in alias.product_slugs:
            if slug not in products:
                issues.append(ValidationIssue(
                    severity="error", code="unknown_alias_product",
                    message=f"별칭 대상 상품이 없습니다: {slug}",
                ))

    for product in bundle.products:
        location = f"products.{product.slug}"
        role_keys = {(role.organization_code, role.role) for role in product.organization_roles}
        if not role_keys:
            issues.append(ValidationIssue(
                severity="error", code="missing_organization_role",
                message="상품에는 기관 역할이 하나 이상 필요합니다.", location=location,
            ))
        for organization_code, _role in role_keys:
            if organization_code not in organizations:
                issues.append(ValidationIssue(
                    severity="error", code="unknown_product_organization",
                    message=f"상품 기관 코드가 없습니다: {organization_code}", location=location,
                ))
        if product.product_type.value == "bank_loan" and not any(
            role.role == OrganizationRole.LENDER for role in product.organization_roles
        ):
            issues.append(ValidationIssue(
                severity="error", code="missing_lender",
                message="은행대출에는 lender 역할이 필요합니다.", location=location,
            ))
        if not product.sources:
            issues.append(ValidationIssue(
                severity="error", code="missing_official_source",
                message="상품에는 공식 출처가 하나 이상 필요합니다.", location=location,
            ))
        if product.application_end_date and product.application_end_date < checked_at.date():
            if product.status != ProductStatus.CLOSED:
                issues.append(ValidationIssue(
                    severity="error", code="expired_product_not_closed",
                    message="신청 종료일이 지났지만 상태가 closed가 아닙니다.", location=location,
                ))
        if product.status == ProductStatus.ACTIVE and not product.summary:
            issues.append(ValidationIssue(
                severity="warning", code="missing_summary",
                message="진행 중 상품에 요약이 없습니다.", location=location,
            ))
        unknown_extra = sorted(set(product.extra_data) - ALLOWED_EXTRA_KEYS)
        if unknown_extra:
            issues.append(ValidationIssue(
                severity="error", code="unknown_extra_data_key",
                message=f"정의되지 않은 extra_data 키: {unknown_extra}", location=location,
            ))
        if any(item.amount_min_krw is not None or item.amount_max_krw is not None for item in product.benefits):
            products_with_amount += 1
        if any(
            item.interest_rate_min_pct is not None or item.interest_rate_max_pct is not None
            for item in product.benefits
        ):
            products_with_rate += 1
        for group in product.eligibility_groups:
            structured_rule_count += len(group.rules)
            for rule in group.rules:
                if rule.field_key not in KNOWN_RULE_FIELDS:
                    issues.append(ValidationIssue(
                        severity="error", code="unknown_rule_field",
                        message=f"정의되지 않은 자격조건 필드: {rule.field_key}", location=location,
                    ))
                if rule.field_key == "industry_code" and "code_system" not in rule.extra_data:
                    issues.append(ValidationIssue(
                        severity="error", code="missing_industry_code_system",
                        message="업종 조건에는 code_system이 필요합니다.", location=location,
                    ))
        for source_record in product.sources:
            source_counts[source_record.data_source_key] += 1
            definition = sources.get(source_record.data_source_key)
            if definition is None:
                issues.append(ValidationIssue(
                    severity="error", code="unknown_product_source",
                    message=f"상품 출처 키가 없습니다: {source_record.data_source_key}",
                    location=location,
                ))
                continue
            age_days = (checked_at - source_record.checked_at).total_seconds() / 86_400
            warning_days = 2 if definition.acquisition_mode == AcquisitionMode.OFFICIAL_API else 10
            if product.status == ProductStatus.ACTIVE and age_days > 30:
                issues.append(ValidationIssue(
                    severity="error", code="stale_active_source",
                    message=f"진행 중 상품의 공식 출처 확인이 {age_days:.0f}일 지났습니다.",
                    location=location,
                ))
            elif product.status == ProductStatus.ACTIVE and age_days > warning_days:
                issues.append(ValidationIssue(
                    severity="warning", code="aging_active_source",
                    message=f"공식 출처를 다시 확인할 시점입니다: {age_days:.0f}일 경과",
                    location=location,
                ))

    statuses = Counter(item.status for item in bundle.products)
    return ValidationReport(
        checked_at=checked_at,
        product_count=len(bundle.products),
        active_count=statuses[ProductStatus.ACTIVE],
        upcoming_count=statuses[ProductStatus.UPCOMING],
        closed_count=statuses[ProductStatus.CLOSED],
        source_counts=dict(sorted(source_counts.items())),
        products_with_amount=products_with_amount,
        products_with_rate=products_with_rate,
        structured_rule_count=structured_rule_count,
        issues=issues,
    )
