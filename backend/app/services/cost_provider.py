from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd


PropertyType = Literal["small_retail", "medium_large_retail", "strata_retail"]
FloorType = Literal["b1", "f1", "f2", "f3", "f4", "f5", "f6_plus"]

OBSERVATION_FILE = "commercial_rent_observations.parquet"
CROSSWALK_FILE = "commercial_rent_crosswalk.parquet"
SOURCE_NAME = "한국부동산원 R-ONE 상업용부동산 임대동향조사"
PROPERTY_TYPE_NAMES = {
    "small_retail": "소규모 상가",
    "medium_large_retail": "중대형 상가",
    "strata_retail": "집합 상가",
}
FLOOR_NAMES = {
    "b1": "지하 1층", "f1": "1층", "f2": "2층", "f3": "3층",
    "f4": "4층", "f5": "5층", "f6_plus": "6층 이상",
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
    property_type: PropertyType
    floor: FloorType
    rentable_area_sqm: float
    unit_converted_rent_krw_sqm: float
    estimated_converted_monthly_rent_krw: float
    annual_conversion_rate: float
    reference_period: str
    survey_area_name: str
    survey_area_distance_km: float
    mapping_method: Literal["nearest_reb_survey_market"]
    source: str = SOURCE_NAME
    disclosure: str = (
        "인근 한국부동산원 표본상권의 전환임대료를 적용한 추정치이며, "
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
        property_type: PropertyType,
        floor: FloorType,
        rentable_area_sqm: float,
    ) -> RentalEstimate | None: ...

    def options(self) -> list[dict[str, object]]: ...


def _cost_options(observations: pd.DataFrame | None = None) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for property_type, name in PROPERTY_TYPE_NAMES.items():
        available = list(FLOOR_NAMES)
        if observations is not None:
            selected = observations.loc[
                observations["property_type"].astype(str).eq(property_type), "floor"
            ].dropna().astype(str)
            available_set = set(selected)
            available = [floor for floor in FLOOR_NAMES if floor in available_set]
        output.append({
            "code": property_type,
            "name": name,
            "floors": [{"code": floor, "name": FLOOR_NAMES[floor]} for floor in available],
        })
    return output


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
    """Read-only runtime provider backed by manually refreshed static Parquet files."""

    REQUIRED_OBSERVATION_COLUMNS = {
        "property_type", "survey_area_name", "floor", "reference_period",
        "unit_converted_rent_krw_sqm", "annual_conversion_rate",
    }
    REQUIRED_CROSSWALK_COLUMNS = {
        "area_code", "property_type", "survey_area_name", "distance_km",
    }

    def __init__(self, observations: pd.DataFrame, crosswalk: pd.DataFrame) -> None:
        missing_observations = sorted(self.REQUIRED_OBSERVATION_COLUMNS - set(observations.columns))
        missing_crosswalk = sorted(self.REQUIRED_CROSSWALK_COLUMNS - set(crosswalk.columns))
        if missing_observations or missing_crosswalk:
            raise RuntimeError(
                "상가 비용 아티팩트 스키마가 올바르지 않습니다. "
                f"observations={missing_observations}, crosswalk={missing_crosswalk}"
            )
        if crosswalk.duplicated(["area_code", "property_type"]).any():
            raise RuntimeError("상가 비용 crosswalk에 area_code/property_type 중복이 있습니다.")
        self.observations = observations.copy()
        self.crosswalk = crosswalk.copy()
        for frame in (self.observations, self.crosswalk):
            for column in ("property_type", "survey_area_name"):
                frame[column] = frame[column].astype(str)
        self.crosswalk["area_code"] = self.crosswalk["area_code"].astype(str)

    @classmethod
    def from_artifact_dir(cls, artifact_dir: Path) -> "ParquetCommercialCostProvider":
        observation_path = artifact_dir / OBSERVATION_FILE
        crosswalk_path = artifact_dir / CROSSWALK_FILE
        if not observation_path.exists() or not crosswalk_path.exists():
            raise FileNotFoundError("상가 비용 Parquet 아티팩트가 없습니다.")
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("상가 비용 체크섬을 확인할 manifest가 없습니다.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for path in (observation_path, crosswalk_path):
            expected = manifest.get("files", {}).get(path.name, {}).get("sha256")
            if not expected:
                raise RuntimeError(f"상가 비용 manifest 항목이 없습니다: {path.name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected:
                raise RuntimeError(f"상가 비용 아티팩트 체크섬이 일치하지 않습니다: {path.name}")
        provider = cls(pd.read_parquet(observation_path), pd.read_parquet(crosswalk_path))
        index_path = artifact_dir / "area_recommendation_index.parquet"
        if index_path.exists():
            area_count = pd.read_parquet(index_path, columns=["area_code"])["area_code"].nunique()
            expected_rows = area_count * 3
            if len(provider.crosswalk) != expected_rows:
                raise RuntimeError(
                    f"상가 비용 매핑 coverage가 부족합니다: expected={expected_rows}, "
                    f"actual={len(provider.crosswalk)}"
                )
        return provider

    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult:
        selected = self.crosswalk
        if area_codes:
            selected = selected.loc[selected["area_code"].isin(map(str, area_codes))]
        rows = tuple(
            CommercialCostObservation(
                area_code=str(row.area_code),
                monthly_rent_krw=None,
                deposit_krw=None,
                unit_area_sqm=None,
                reference_period=str(self.observations["reference_period"].max()),
                source=SOURCE_NAME,
                reliability=None,
            )
            for row in selected[["area_code"]].drop_duplicates().itertuples(index=False)
        )
        return CommercialCostResult(availability="available", observations=rows)

    def options(self) -> list[dict[str, object]]:
        return _cost_options(self.observations)

    def estimate(
        self,
        area_code: str,
        property_type: PropertyType,
        floor: FloorType,
        rentable_area_sqm: float,
    ) -> RentalEstimate | None:
        if not math.isfinite(rentable_area_sqm) or rentable_area_sqm <= 0:
            raise ValueError("임대면적은 0보다 커야 합니다.")
        mapping = self.crosswalk.loc[
            self.crosswalk["area_code"].eq(str(area_code))
            & self.crosswalk["property_type"].eq(property_type)
        ]
        if mapping.empty:
            return None
        mapped = mapping.iloc[0]
        rows = self.observations.loc[
            self.observations["property_type"].eq(property_type)
            & self.observations["survey_area_name"].eq(str(mapped["survey_area_name"]))
        ].copy()
        if rows.empty:
            return None
        latest = str(rows["reference_period"].max())
        rows = rows.loc[rows["reference_period"].astype(str).eq(latest)]
        selected = rows.loc[rows["floor"].astype(str).eq(floor)]
        if selected.empty and floor != "f1":
            first = rows.loc[rows["floor"].astype(str).eq("f1")]
            target_ratio = rows.loc[rows["floor"].astype(str).eq(floor), "floor_utility_ratio"] \
                if "floor_utility_ratio" in rows else pd.Series(dtype="float64")
            if not first.empty and not target_ratio.dropna().empty:
                selected = first.copy()
                selected["unit_converted_rent_krw_sqm"] = (
                    float(first.iloc[0]["unit_converted_rent_krw_sqm"])
                    * float(target_ratio.dropna().iloc[0])
                )
        if selected.empty:
            return None
        row = selected.iloc[0]
        unit_rent = float(row["unit_converted_rent_krw_sqm"])
        conversion_rate = float(row["annual_conversion_rate"])
        if conversion_rate > 1:
            conversion_rate /= 100.0
        return RentalEstimate(
            property_type=property_type,
            floor=floor,
            rentable_area_sqm=round(float(rentable_area_sqm), 4),
            unit_converted_rent_krw_sqm=round(unit_rent, 2),
            estimated_converted_monthly_rent_krw=round(unit_rent * rentable_area_sqm, 2),
            annual_conversion_rate=round(conversion_rate, 6),
            reference_period=latest,
            survey_area_name=str(mapped["survey_area_name"]),
            survey_area_distance_km=round(float(mapped["distance_km"]), 3),
            mapping_method="nearest_reb_survey_market",
        )


class UnavailableCostProvider:
    def get_area_costs(self, area_codes: list[str]) -> CommercialCostResult:
        del area_codes
        return CommercialCostResult(
            availability="unavailable",
            reason=(
                "상가 임대료 정적 산출물이 없습니다. REB_API_KEY를 설정한 뒤 "
                "수동 갱신 스크립트를 실행하면 예산 점수가 활성화됩니다."
            ),
        )

    def estimate(
        self,
        area_code: str,
        property_type: PropertyType,
        floor: FloorType,
        rentable_area_sqm: float,
    ) -> RentalEstimate | None:
        del area_code, property_type, floor, rentable_area_sqm
        return None

    def options(self) -> list[dict[str, object]]:
        return _cost_options()
