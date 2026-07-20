from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd


FloorType = Literal["all", "f1", "non_f1"]

OBSERVATION_FILE = "commercial_rent_observations.parquet"
SOURCE_NAME = "서울시 상권분석서비스 임대시세(서울신용보증재단 보증 고객 통계)"
FLOOR_NAMES: dict[FloorType, str] = {
    "all": "전체 층 평균",
    "f1": "1층",
    "non_f1": "1층 외",
}


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


@dataclass(frozen=True)
class RentalEstimate:
    area_code: str
    area_name: str
    admin_dong_name: str
    rent_basis_geography: Literal["admin_dong", "district"]
    rent_basis_name: str
    geography_fallback_used: bool
    floor: FloorType
    rent_basis_floor: FloorType
    fallback_used: bool
    rentable_area_sqm: float
    unit_converted_rent_krw_sqm: float
    estimated_converted_monthly_rent_krw: float
    annual_conversion_rate: float
    reference_period: str
    source: str = SOURCE_NAME
    disclosure: str = (
        "해당 상권이 속한 행정동의 서울시 환산임대시세를 적용한 추정치이며, "
        "관리비·부가가치세는 포함하지 않습니다."
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LeasePlan:
    estimated_converted_monthly_rent_krw: float
    deposit_krw: float | None
    cash_monthly_rent_krw: float | None
    annual_cash_rent_krw: float | None
    first_year_cash_outlay_krw: float | None
    refundable_deposit_krw: float | None
    remaining_startup_budget_krw: float | None
    deposit_share_of_budget: float | None
    annual_conversion_rate: float
    disclosure: str = (
        "보증금은 반환 가능한 자금으로 별도 표시했습니다. 실제 계약의 관리비·부가가치세·"
        "권리금·인테리어비는 포함하지 않습니다."
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CommercialCostProvider(Protocol):
    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult: ...

    def estimate(
        self,
        area_code: str,
        floor: FloorType,
        rentable_area_sqm: float,
    ) -> RentalEstimate | None: ...

    def options(self) -> list[dict[str, str]]: ...


def _cost_options() -> list[dict[str, str]]:
    return [{"code": code, "name": name} for code, name in FLOOR_NAMES.items()]


def calculate_budget_fit(monthly_limit_krw: float, estimated_monthly_krw: float) -> float:
    if monthly_limit_krw <= 0 or estimated_monthly_krw <= 0:
        raise ValueError("월 임대료 한도와 예상 임대료는 0보다 커야 합니다.")
    return min(100.0, monthly_limit_krw / estimated_monthly_krw * 100.0)


def calculate_lease_plan(
    estimate: RentalEstimate,
    *,
    deposit_krw: float | None,
    total_startup_budget_krw: float | None,
) -> LeasePlan:
    cash_monthly: float | None = None
    annual_cash: float | None = None
    first_year: float | None = None
    remaining: float | None = None
    share: float | None = None
    if deposit_krw is not None:
        cash_monthly = max(
            0.0,
            estimate.estimated_converted_monthly_rent_krw
            - deposit_krw * estimate.annual_conversion_rate / 12.0,
        )
        annual_cash = cash_monthly * 12.0
        first_year = deposit_krw + annual_cash
        if total_startup_budget_krw is not None:
            remaining = total_startup_budget_krw - first_year
            share = deposit_krw / total_startup_budget_krw if total_startup_budget_krw else None
    return LeasePlan(
        estimated_converted_monthly_rent_krw=estimate.estimated_converted_monthly_rent_krw,
        deposit_krw=deposit_krw,
        cash_monthly_rent_krw=cash_monthly,
        annual_cash_rent_krw=annual_cash,
        first_year_cash_outlay_krw=first_year,
        refundable_deposit_krw=deposit_krw,
        remaining_startup_budget_krw=remaining,
        deposit_share_of_budget=share,
        annual_conversion_rate=estimate.annual_conversion_rate,
    )


class ParquetCommercialCostProvider:
    """Read-only runtime provider backed by a manually refreshed static Parquet file."""

    REQUIRED_OBSERVATION_COLUMNS = {
        "area_code", "area_name", "admin_dong_name", "rent_basis_geography",
        "rent_basis_name", "floor", "reference_period",
        "unit_converted_rent_krw_sqm", "annual_conversion_rate",
    }

    def __init__(self, observations: pd.DataFrame) -> None:
        missing = sorted(self.REQUIRED_OBSERVATION_COLUMNS - set(observations.columns))
        if missing:
            raise RuntimeError(f"상가 비용 아티팩트 스키마가 올바르지 않습니다: {missing}")
        if observations.duplicated(["area_code", "reference_period", "floor"]).any():
            raise RuntimeError("상가 비용 아티팩트에 area/period/floor 중복이 있습니다.")
        invalid_floors = set(observations["floor"].dropna().astype(str)) - set(FLOOR_NAMES)
        if invalid_floors:
            raise RuntimeError(f"상가 비용 아티팩트의 층 코드가 올바르지 않습니다: {sorted(invalid_floors)}")
        self.observations = observations.copy()
        for column in (
            "area_code", "area_name", "admin_dong_name", "rent_basis_geography",
            "rent_basis_name", "floor", "reference_period",
        ):
            self.observations[column] = self.observations[column].astype(str)
        self.latest_period = str(self.observations["reference_period"].max())

    @classmethod
    def from_artifact_dir(cls, artifact_dir: Path) -> "ParquetCommercialCostProvider":
        observation_path = artifact_dir / OBSERVATION_FILE
        if not observation_path.exists():
            raise FileNotFoundError("상가 비용 Parquet 아티팩트가 없습니다.")
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("상가 비용 체크섬을 확인할 manifest가 없습니다.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = manifest.get("files", {}).get(observation_path.name, {}).get("sha256")
        if not expected:
            raise RuntimeError(f"상가 비용 manifest 항목이 없습니다: {observation_path.name}")
        digest = hashlib.sha256(observation_path.read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError(f"상가 비용 아티팩트 체크섬이 일치하지 않습니다: {observation_path.name}")
        provider = cls(pd.read_parquet(observation_path))
        index_path = artifact_dir / "area_recommendation_index.parquet"
        if index_path.exists():
            area_count = pd.read_parquet(index_path, columns=["area_code"])["area_code"].nunique()
            latest = provider.observations["reference_period"].max()
            all_count = provider.observations.loc[
                provider.observations["reference_period"].eq(latest)
                & provider.observations["floor"].eq("all"),
                "area_code",
            ].nunique()
            if all_count != area_count:
                raise RuntimeError(
                    f"상가 비용 전체층 coverage가 부족합니다: expected={area_count}, actual={all_count}"
                )
        return provider

    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult:
        selected = self.observations
        if area_codes:
            selected = selected.loc[selected["area_code"].isin(map(str, area_codes))]
        latest = self.latest_period
        rows = tuple(
            CommercialCostObservation(
                area_code=str(row.area_code),
                monthly_rent_krw=None,
                deposit_krw=None,
                unit_area_sqm=None,
                reference_period=latest,
                source=SOURCE_NAME,
                reliability=None,
            )
            for row in selected[["area_code"]].drop_duplicates().itertuples(index=False)
        )
        return CommercialCostResult(availability="available", observations=rows)

    def options(self) -> list[dict[str, str]]:
        return _cost_options()

    def estimate(
        self,
        area_code: str,
        floor: FloorType,
        rentable_area_sqm: float,
    ) -> RentalEstimate | None:
        if not math.isfinite(rentable_area_sqm) or rentable_area_sqm <= 0:
            raise ValueError("임대면적은 0보다 커야 합니다.")
        if floor not in FLOOR_NAMES:
            raise ValueError(f"알 수 없는 층 구분입니다: {floor}")
        rows = self.observations.loc[self.observations["area_code"].eq(str(area_code))].copy()
        if rows.empty:
            return None
        latest = str(rows["reference_period"].max())
        rows = rows.loc[rows["reference_period"].eq(latest)]
        selected = rows.loc[rows["floor"].eq(floor)]
        basis_floor: FloorType = floor
        if selected.empty and floor != "all":
            selected = rows.loc[rows["floor"].eq("all")]
            basis_floor = "all"
        if selected.empty:
            return None
        row = selected.iloc[0]
        unit_rent = float(row["unit_converted_rent_krw_sqm"])
        conversion_rate = float(row["annual_conversion_rate"])
        if conversion_rate > 1:
            conversion_rate /= 100.0
        return RentalEstimate(
            area_code=str(row["area_code"]),
            area_name=str(row["area_name"]),
            admin_dong_name=str(row["admin_dong_name"]),
            rent_basis_geography=str(row["rent_basis_geography"]),
            rent_basis_name=str(row["rent_basis_name"]),
            geography_fallback_used=str(row["rent_basis_geography"]) == "district",
            floor=floor,
            rent_basis_floor=basis_floor,
            fallback_used=basis_floor != floor,
            rentable_area_sqm=round(float(rentable_area_sqm), 4),
            unit_converted_rent_krw_sqm=round(unit_rent, 2),
            estimated_converted_monthly_rent_krw=round(unit_rent * rentable_area_sqm, 2),
            annual_conversion_rate=round(conversion_rate, 6),
            reference_period=latest,
            disclosure=(
                "해당 상권이 속한 자치구의 서울시 환산임대시세를 적용한 대체 추정치이며, "
                "관리비·부가가치세는 포함하지 않습니다."
                if str(row["rent_basis_geography"]) == "district"
                else "해당 상권이 속한 행정동의 서울시 환산임대시세를 적용한 추정치이며, "
                "관리비·부가가치세는 포함하지 않습니다."
            ),
        )


class UnavailableCostProvider:
    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult:
        del area_codes
        return CommercialCostResult(
            availability="unavailable",
            reason=(
                "서울시 상권분석서비스 임대시세 정적 산출물이 없습니다. "
                "수동 갱신 스크립트를 실행하면 예산 점수가 활성화됩니다."
            ),
        )

    def estimate(
        self,
        area_code: str,
        floor: FloorType,
        rentable_area_sqm: float,
    ) -> RentalEstimate | None:
        del area_code, floor, rentable_area_sqm
        return None

    def options(self) -> list[dict[str, str]]:
        return _cost_options()
