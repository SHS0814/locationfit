from __future__ import annotations

from datetime import date

from backend.app.schemas.finance import FinancePlanRequest


MSS_2026_SOURCE = "https://www.mss.go.kr/site/smba/ex/bbs/View.do?bcIdx=1069735&cbIdx=310"
KINFA_OPERATING_SOURCE = "https://www.kinfa.or.kr/financialProduct/smileFinanceFunds.do"
KINFA_PRIVATE_SOURCE = "https://www.kinfa.or.kr/financialProduct/privateBusinessFunds.do"
SOURCE_CHECKED_AT = "2026-07-21"


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


def _semas_candidate(payload: FinancePlanRequest) -> dict[str, object]:
    eligibility = payload.eligibility
    reasons: list[str] = []
    checks: list[str] = []
    if eligibility.is_small_business is False:
        status = "not_eligible"
        reasons.append("소상공인 기본요건에 해당하지 않는다고 입력했습니다.")
    elif eligibility.has_policy_excluded_industry is True:
        status = "not_eligible"
        reasons.append("정책자금 융자제외 업종이라고 입력했습니다.")
    else:
        status = "needs_review"
        reasons.append("2026년 정책자금은 세부 자금별 업력·신용·매출 요건과 접수상태가 다릅니다.")
        if eligibility.is_small_business is None:
            checks.append("소상공인 확인서 및 상시근로자·매출 기준")
        if eligibility.business_status == "pre_startup":
            checks.append("사업자등록 이후 신청 가능한 세부 자금인지 확인")
        if eligibility.has_policy_excluded_industry is None:
            checks.append("2026년 융자제외 업종 해당 여부")
        checks.append("정책자금 온라인 접수일과 세부 자금별 신청요건")
    return {
        "program_id": "mss-small-business-policy-fund-2026",
        "name": "2026 소상공인 정책자금",
        "provider": "중소벤처기업부·소상공인시장진흥공단",
        "status": status,
        "reasons": reasons,
        "checks_required": checks,
        "source_title": "2026년 소상공인 정책자금 융자사업 공고(3차 변경)",
        "source_url": MSS_2026_SOURCE,
        "source_checked_at": SOURCE_CHECKED_AT,
    }


def _vulnerability_qualifies(value: str) -> bool:
    return value in {"low_credit", "basic_livelihood", "near_poverty", "earned_income_tax_credit"}


def _kinfa_candidate(payload: FinancePlanRequest) -> dict[str, object]:
    eligibility = payload.eligibility
    operating_ready = eligibility.business_status == "operating" and (eligibility.business_age_months or 0) >= 3
    is_pre_startup = eligibility.business_status == "pre_startup"
    program_id = "kinfa-private-startup-fund" if is_pre_startup else "kinfa-microfinance-operating-fund"
    name = "민간사업수행기관 창업·운영자금" if is_pre_startup else "미소금융 운영자금"
    source_url = KINFA_PRIVATE_SOURCE if is_pre_startup else KINFA_OPERATING_SOURCE
    reasons: list[str] = []
    checks: list[str] = []
    if eligibility.has_policy_excluded_industry is True:
        status = "not_eligible"
        reasons.append("융자제외 업종이라고 입력해 서민금융 창업·운영자금 기본조건과 맞지 않습니다.")
    elif eligibility.vulnerability == "none":
        status = "not_eligible"
        reasons.append("저신용·기초생활·차상위·근로장려금 요건에 해당하지 않는다고 입력했습니다.")
    elif not is_pre_startup and not operating_ready:
        status = "not_eligible"
        reasons.append("미소금융 운영자금은 동일 사업을 3개월 이상 운영한 자영업자 등이 대상입니다.")
    elif _vulnerability_qualifies(eligibility.vulnerability):
        status = "basic_fit"
        reasons.append("입력한 금융취약 요건이 공식 지원대상의 기본조건과 부합합니다.")
        checks.extend(["기관 상담 및 여신심사", "소득·신용·자격 증빙", "자금용도와 중복지원 여부"])
    else:
        status = "needs_review"
        reasons.append("금융취약 요건을 아직 확인하지 않아 대상 여부를 판단할 수 없습니다.")
        checks.extend(["개인신용평점 하위 20%, 기초생활·차상위 또는 근로장려금 자격 여부", "기관 상담 및 여신심사"])
    if eligibility.has_policy_excluded_industry is None:
        checks.append("융자제외 업종 및 지원제한 사유 해당 여부")
    return {
        "program_id": program_id,
        "name": name,
        "provider": "서민금융진흥원",
        "status": status,
        "reasons": reasons,
        "checks_required": list(dict.fromkeys(checks)),
        "source_title": f"서민금융진흥원 {name} 공식 안내",
        "source_url": source_url,
        "source_checked_at": SOURCE_CHECKED_AT,
    }


class FinancePlanService:
    def create_plan(self, payload: FinancePlanRequest) -> dict[str, object]:
        return {
            "funding": calculate_funding(payload),
            "policy_candidates": [_semas_candidate(payload), _kinfa_candidate(payload)],
            "disclosure": (
                f"{date.fromisoformat(SOURCE_CHECKED_AT).isoformat()} 공식 안내 기준의 1차 후보 판정입니다. "
                "대출 가능 여부·한도·금리는 접수 시점의 공고와 기관 심사로 확정되며, 부가세·중개보수·공과금은 계산에 포함되지 않습니다."
            ),
        }

