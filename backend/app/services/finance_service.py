from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.app.db.models import (
    OrganizationRole,
    ProductStatus,
    ProductType,
    RuleOperator,
)
from backend.app.financial_catalog.contracts import (
    CatalogBundle,
    EligibilityRuleRecord,
    ProductRecord,
)
from backend.app.schemas.finance import FinancePlanRequest


UNKNOWN = object()
ROLE_PRIORITY = {
    OrganizationRole.OPERATOR: 0,
    OrganizationRole.LENDER: 1,
    OrganizationRole.GUARANTOR: 2,
    OrganizationRole.AUTHORITY: 3,
    OrganizationRole.PUBLISHER: 4,
}
MATCH_PRIORITY = {"basic_fit": 0, "needs_review": 1, "not_eligible": 2}
TYPE_PRIORITY = {
    ProductType.BANK_LOAN: 0,
    ProductType.POLICY_FUND: 1,
    ProductType.GUARANTEE: 2,
    ProductType.SUPPORT_PROGRAM: 3,
}


def calculate_funding(payload: FinancePlanRequest) -> dict[str, int | float]:
    candidate = payload.candidate
    costs = payload.additional_costs
    one_time = candidate.key_money_krw
    annual_occupancy = 12 * (candidate.monthly_rent_krw + candidate.management_fee_krw)
    additional = (
        costs.interior_krw + costs.equipment_krw + costs.initial_inventory_krw
        + costs.working_capital_krw + costs.other_krw
    )
    total = candidate.deposit_krw + one_time + annual_occupancy + additional
    own_capital = payload.eligibility.own_capital_krw
    return {
        "refundable_deposit_krw": candidate.deposit_krw,
        "one_time_nonrefundable_krw": one_time,
        "annual_occupancy_cost_krw": annual_occupancy,
        "additional_startup_cost_krw": additional,
        "total_first_year_cash_need_krw": total,
        "own_capital_krw": own_capital,
        "funding_gap_krw": max(0, total - own_capital),
        "own_capital_ratio": round(own_capital / total, 4) if total else 1.0,
    }


def _applicant_context(payload: FinancePlanRequest) -> dict[str, Any]:
    eligibility = payload.eligibility
    return {
        "region_code": "11",
        "business_status": eligibility.business_status,
        "business_age_months": (
            eligibility.business_age_months
            if eligibility.business_status == "operating"
            else 0
        ),
        "is_small_business": eligibility.is_small_business,
        "vulnerability_category": (
            None if eligibility.vulnerability == "unknown" else eligibility.vulnerability
        ),
        "has_miso_good_repayment_history": eligibility.has_miso_good_repayment_history,
    }


def _evaluate_rule(rule: EligibilityRuleRecord, context: dict[str, Any]) -> bool | None:
    actual = context.get(rule.field_key, UNKNOWN)
    if actual is UNKNOWN or actual is None:
        return None
    expected = rule.value
    operator = rule.operator
    try:
        if rule.field_key == "region_code" and operator == RuleOperator.IN:
            allowed = set(expected if isinstance(expected, list) else [expected])
            return actual in allowed or "KR" in allowed
        if operator == RuleOperator.EQUALS:
            return actual == expected
        if operator == RuleOperator.NOT_EQUALS:
            return actual != expected
        if operator == RuleOperator.IN:
            return actual in expected
        if operator == RuleOperator.NOT_IN:
            return actual not in expected
        if operator == RuleOperator.GREATER_THAN:
            return actual > expected
        if operator == RuleOperator.GREATER_THAN_OR_EQUAL:
            return actual >= expected
        if operator == RuleOperator.LESS_THAN:
            return actual < expected
        if operator == RuleOperator.LESS_THAN_OR_EQUAL:
            return actual <= expected
        if operator == RuleOperator.BETWEEN:
            return expected[0] <= actual <= expected[1]
        if operator == RuleOperator.CONTAINS:
            return expected in actual
    except (IndexError, KeyError, TypeError):
        return None
    return None


def _match_product(
    product: ProductRecord,
    payload: FinancePlanRequest,
) -> tuple[str, list[str], list[str]]:
    if (
        product.product_type == ProductType.POLICY_FUND
        and payload.eligibility.has_policy_excluded_industry is True
    ):
        return (
            "not_eligible",
            ["정책자금 융자제외 업종에 해당한다고 입력했습니다."],
            [],
        )

    context = _applicant_context(payload)
    group_states: list[str] = []
    failed_descriptions: list[str] = []
    unknown_descriptions: list[str] = []
    for group in product.eligibility_groups:
        results = [(_evaluate_rule(rule, context), rule.description) for rule in group.rules]
        failures = [description for result, description in results if result is False]
        unknowns = [description for result, description in results if result is None]
        if failures:
            group_states.append("failed")
            failed_descriptions.extend(failures)
        elif unknowns:
            group_states.append("unknown")
            unknown_descriptions.extend(unknowns)
        else:
            group_states.append("passed")

    if "passed" in group_states:
        status = "basic_fit"
        reasons = ["입력한 정보가 구조화된 공개 기본조건과 부합합니다."]
    elif "unknown" in group_states:
        status = "needs_review"
        reasons = ["입력 정보만으로 공개 기본조건 일부를 확인할 수 없습니다."]
    elif group_states:
        status = "not_eligible"
        reasons = list(dict.fromkeys(failed_descriptions))
    else:
        status = "needs_review"
        reasons = ["구조화된 기본조건이 없어 공식 원문의 신청대상을 확인해야 합니다."]
        unknown_descriptions.append("공식 원문의 신청대상과 금융기관 심사조건")

    checks = list(dict.fromkeys(unknown_descriptions))
    eligibility_notes = product.extra_data.get("eligibility_notes")
    if eligibility_notes and status != "not_eligible":
        checks.append(str(eligibility_notes))
    if product.status == ProductStatus.UPCOMING:
        status = "needs_review"
        checks.append("신청 개시일과 현재 접수 여부")
    elif product.status == ProductStatus.UNKNOWN:
        status = "needs_review"
        checks.append("현재 접수상태와 별도 시행공고")
    return status, list(dict.fromkeys(reasons)), list(dict.fromkeys(checks))


def _provider(product: ProductRecord, organizations: dict[str, str]) -> str:
    roles = sorted(
        product.organization_roles,
        key=lambda item: (ROLE_PRIORITY[item.role], item.organization_code),
    )
    if not roles:
        return "제공기관 확인 필요"
    return organizations.get(roles[0].organization_code, roles[0].organization_code)


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _candidate_payload(
    product: ProductRecord,
    payload: FinancePlanRequest,
    organizations: dict[str, str],
) -> dict[str, Any]:
    match_status, reasons, checks = _match_product(product, payload)
    source = max(product.sources, key=lambda item: item.checked_at)
    return {
        "program_id": product.slug,
        "name": product.name,
        "provider": _provider(product, organizations),
        "product_type": product.product_type.value,
        "catalog_status": product.status.value,
        "summary": product.summary,
        "status": match_status,
        "reasons": reasons,
        "checks_required": checks,
        "benefits": [{
            "benefit_type": benefit.benefit_type.value,
            "amount_min_krw": benefit.amount_min_krw,
            "amount_max_krw": benefit.amount_max_krw,
            "interest_rate_min_pct": _number(benefit.interest_rate_min_pct),
            "interest_rate_max_pct": _number(benefit.interest_rate_max_pct),
            "guarantee_rate_pct": _number(benefit.guarantee_rate_pct),
            "interest_subsidy_rate_pct": _number(benefit.interest_subsidy_rate_pct),
            "guarantee_fee_rate_pct": _number(benefit.guarantee_fee_rate_pct),
            "term_min_months": benefit.term_min_months,
            "term_max_months": benefit.term_max_months,
            "grace_period_months": benefit.grace_period_months,
            "original_text": benefit.original_text,
        } for benefit in product.benefits],
        "application_url": product.application_url,
        "application_end_date": (
            product.application_end_date.isoformat()
            if product.application_end_date is not None
            else None
        ),
        "source_title": source.title,
        "source_url": source.official_url,
        "source_checked_at": source.checked_at.date().isoformat(),
    }


class FinancePlanService:
    def create_plan(
        self,
        payload: FinancePlanRequest,
        catalog: CatalogBundle,
    ) -> dict[str, object]:
        organizations = {item.code: item.name for item in catalog.organizations}
        candidates = [
            _candidate_payload(product, payload, organizations)
            for product in catalog.products
            if product.status in {
                ProductStatus.ACTIVE,
                ProductStatus.UPCOMING,
                ProductStatus.UNKNOWN,
            }
            and product.sources
        ]
        candidates.sort(key=lambda item: (
            MATCH_PRIORITY[str(item["status"])],
            TYPE_PRIORITY[ProductType(str(item["product_type"]))],
            str(item["name"]),
        ))
        return {
            "funding": calculate_funding(payload),
            "policy_candidates": candidates,
            "disclosure": (
                f"{date.today().isoformat()} DB 카탈로그 기준의 기본조건 비교입니다. "
                "기본조건 부합은 승인 가능성을 의미하지 않으며 실제 한도·금리·보증 여부는 "
                "접수 시점 공고와 금융기관·보증기관 심사로 확정됩니다."
            ),
        }
