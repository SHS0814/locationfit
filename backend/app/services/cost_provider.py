from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class CommercialCostObservation:
    area_code: str
    monthly_rent_krw: float | None
    deposit_krw: float | None
    unit_area_sqm: float | None
    reference_period: str
    source: str
    reliability: float | None


@dataclass(frozen=True)
class CommercialCostResult:
    availability: Literal["available", "unavailable"]
    observations: tuple[CommercialCostObservation, ...] = ()
    reason: str | None = None


class CommercialCostProvider(Protocol):
    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult: ...


class UnavailableCostProvider:
    """v1 provider: makes the missing commercial-cost source explicit and testable."""

    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult:
        del area_codes
        return CommercialCostResult(
            availability="unavailable",
            reason="상가 임대료·보증금 데이터 공급자가 아직 연결되지 않았습니다.",
        )
