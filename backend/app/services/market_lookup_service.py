from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd


LookupGroup = Literal["area", "industry", "district", "admin_dong"]
LookupMetric = Literal[
    "sales", "closing_rate", "opening_rate", "growth_rate",
    "store_count", "store_density", "floating_population",
    "resident_population", "worker_population",
]
LookupOrder = Literal["desc", "asc"]


METRICS: dict[str, dict[str, str]] = {
    "sales": {
        "column": "recent_4q_average_sales",
        "label": "최근 4분기 분기 평균 추정매출",
        "unit": "krw",
        "source": "evidence",
        "aggregation": "sum",
    },
    "closing_rate": {
        "column": "closing_rate",
        "label": "최근 폐업률",
        "unit": "ratio",
        "source": "evidence",
        "aggregation": "store_weighted_mean",
    },
    "opening_rate": {
        "column": "opening_rate",
        "label": "최근 개업률",
        "unit": "ratio",
        "source": "evidence",
        "aggregation": "store_weighted_mean",
    },
    "growth_rate": {
        "column": "recent_4q_growth_rate",
        "label": "최근 4분기 매출 성장률",
        "unit": "ratio",
        "source": "evidence",
        "aggregation": "sales_growth",
    },
    "store_count": {
        "column": "recent_store_count",
        "label": "최근 점포 수",
        "unit": "count",
        "source": "evidence",
        "aggregation": "sum",
    },
    "store_density": {
        "column": "same_industry_store_density",
        "label": "동종업종 점포 밀도",
        "unit": "count_per_sqkm",
        "source": "evidence",
        "aggregation": "mean",
    },
    "floating_population": {
        "column": "floating_population",
        "label": "평균 유동인구",
        "unit": "people",
        "source": "profile",
        "aggregation": "sum",
    },
    "resident_population": {
        "column": "resident_population",
        "label": "평균 상주인구",
        "unit": "people",
        "source": "profile",
        "aggregation": "sum",
    },
    "worker_population": {
        "column": "worker_population",
        "label": "평균 직장인구",
        "unit": "people",
        "source": "profile",
        "aggregation": "sum",
    },
}

GROUP_LABELS = {
    "area": "상권",
    "industry": "업종",
    "district": "자치구",
    "admin_dong": "행정동",
}


class MarketLookupService:
    def __init__(self, index: pd.DataFrame, evidence: pd.DataFrame, data_period: dict[str, str]) -> None:
        self.index = index.copy()
        self.evidence = evidence.copy()
        self.data_period = data_period
        self.index["area_code"] = self.index["area_code"].astype(str)
        self.evidence["area_code"] = self.evidence["area_code"].astype(str)
        self.evidence["industry_code"] = self.evidence["industry_code"].astype(str)

    def rank(
        self,
        *,
        group_by: LookupGroup,
        metric: LookupMetric,
        top_n: int = 10,
        order: LookupOrder = "desc",
        district_name: str | None = None,
        admin_dong_name: str | None = None,
        industry_code: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= top_n <= 50:
            raise ValueError("조회 개수는 1~50 사이여야 합니다.")
        spec = METRICS[metric]
        if spec["source"] == "profile" and group_by == "industry":
            raise ValueError(f"{spec['label']}은 업종별로 제공되지 않고 상권 단위로만 제공됩니다.")
        if spec["source"] == "profile" and industry_code is not None:
            raise ValueError(f"{spec['label']}은 업종 필터를 적용할 수 없습니다.")

        area_attributes = self.index[[
            "area_code", "area_name", "district_name", "admin_dong_name", "area_type_name",
            "floating_population", "resident_population", "worker_population",
        ]].copy()
        self._validate_filters(area_attributes, district_name, admin_dong_name, industry_code)

        if spec["source"] == "evidence":
            frame = self.evidence.merge(
                area_attributes[["area_code", "district_name", "admin_dong_name", "area_type_name"]],
                on="area_code",
                how="left",
                validate="many_to_one",
            )
        else:
            frame = area_attributes
        frame = self._apply_filters(frame, district_name, admin_dong_name, industry_code)

        group_columns = self._group_columns(group_by)
        population = self._aggregate(frame, group_columns, spec)
        population = population.loc[population["metric_value"].notna()].copy()
        if population.empty:
            raise ValueError("조건에 맞는 관측 데이터가 없습니다.")
        distribution = self._distribution(population["metric_value"], spec["unit"])
        rows = population.sort_values(
            ["metric_value", *group_columns],
            ascending=[order == "asc", *([True] * len(group_columns))],
            kind="stable",
        ).head(top_n).reset_index(drop=True)

        filters = {
            key: value
            for key, value in {
                "district_name": district_name,
                "admin_dong_name": admin_dong_name,
                "industry_code": industry_code,
            }.items()
            if value is not None
        }
        industry_names = self.evidence.set_index("industry_code")["industry_name"].to_dict()
        if industry_code:
            filters["industry_name"] = str(industry_names[industry_code])

        result_rows = [
            self._serialize_row(row, group_by, spec["unit"], rank, distribution)
            for rank, (_, row) in enumerate(rows.iterrows(), start=1)
        ]
        direction = "높은" if order == "desc" else "낮은"
        uses_dong = group_by == "admin_dong" or admin_dong_name is not None
        disclosure_parts = []
        if uses_dong:
            disclosure_parts.append(
                "동 단위 조회는 서울시 상권영역 데이터의 대표 행정동 기준이며 법정동 경계 집계가 아닙니다."
            )
        disclosure_parts.append(
            "관측 상권은 선택한 지역 안에서 해당 업종과 지표 값이 존재해 집계에 실제 포함된 고유 서울시 상권입니다."
        )
        disclosure_parts.extend([
            "매출은 최근 4개 관측 분기의 분기 평균 추정매출이고, 관측된 지원 상권·업종을 합산합니다.",
            "폐업률·개업률은 최근 점포 수 가중평균입니다.",
            "평균·중앙값·표준편차는 필터 적용 후 순위를 매긴 전체 조회 대상 기준이며 표준편차는 모집단 방식입니다.",
        ])
        return {
            "title": f"{spec['label']} 기준 {direction} {GROUP_LABELS[group_by]} Top {len(result_rows)}",
            "group_by": group_by,
            "metric": metric,
            "metric_label": spec["label"],
            "metric_unit": spec["unit"],
            "order": order,
            "filters": filters,
            "data_period": self._metric_period(metric, spec),
            "distribution": distribution,
            "rows": result_rows,
            "geographic_basis": "상권별 대표 행정동" if uses_dong else "서울시 상권영역",
            "disclosure": " ".join(disclosure_parts),
        }

    def _validate_filters(
        self,
        area_attributes: pd.DataFrame,
        district_name: str | None,
        admin_dong_name: str | None,
        industry_code: str | None,
    ) -> None:
        if district_name and district_name not in set(area_attributes["district_name"].dropna().astype(str)):
            raise ValueError(f"지원하지 않는 자치구입니다: {district_name}")
        if industry_code and industry_code not in set(self.evidence["industry_code"]):
            raise ValueError(f"지원하지 않는 업종 코드입니다: {industry_code}")
        if not admin_dong_name:
            return
        matching = area_attributes.loc[
            area_attributes["admin_dong_name"].eq(admin_dong_name), "district_name"
        ].dropna().astype(str).unique().tolist()
        if not matching:
            raise ValueError(f"지원하지 않는 행정동입니다: {admin_dong_name}")
        if district_name and district_name not in matching:
            raise ValueError(f"{district_name}에 {admin_dong_name} 행정동 데이터가 없습니다.")
        if not district_name and len(matching) > 1:
            districts = ", ".join(sorted(matching))
            raise ValueError(f"{admin_dong_name}은 여러 자치구({districts})에 있습니다. 자치구를 함께 알려주세요.")

    def _metric_period(self, metric: LookupMetric, spec: dict[str, str]) -> str:
        if spec["source"] == "profile":
            return self.data_period.get("profile", "")
        latest = int(pd.to_numeric(self.evidence["latest_observed_quarter"], errors="coerce").max())
        latest_label = f"{latest // 10}Q{latest % 10}"
        if metric in {"store_count", "store_density"}:
            return latest_label
        position = (latest // 10) * 4 + (latest % 10) - 1
        start_position = position - 3
        start_label = f"{start_position // 4}Q{start_position % 4 + 1}"
        return f"{start_label}~{latest_label}"

    @staticmethod
    def _apply_filters(
        frame: pd.DataFrame,
        district_name: str | None,
        admin_dong_name: str | None,
        industry_code: str | None,
    ) -> pd.DataFrame:
        selected = frame
        if district_name:
            selected = selected.loc[selected["district_name"].eq(district_name)]
        if admin_dong_name:
            selected = selected.loc[selected["admin_dong_name"].eq(admin_dong_name)]
        if industry_code and "industry_code" in selected:
            selected = selected.loc[selected["industry_code"].eq(industry_code)]
        return selected.copy()

    @staticmethod
    def _group_columns(group_by: LookupGroup) -> list[str]:
        return {
            "area": ["area_code", "area_name", "district_name", "admin_dong_name"],
            "industry": ["industry_code", "industry_name"],
            "district": ["district_name"],
            "admin_dong": ["district_name", "admin_dong_name"],
        }[group_by]

    @staticmethod
    def _aggregate(frame: pd.DataFrame, groups: list[str], spec: dict[str, str]) -> pd.DataFrame:
        column = spec["column"]
        usable = frame.loc[frame[column].notna()].copy()
        grouped = usable.groupby(groups, observed=True, sort=False, dropna=False)
        base = grouped.agg(
            observation_count=(column, "count"),
            area_count=("area_code", "nunique"),
        ).reset_index()
        aggregation = spec["aggregation"]
        if aggregation == "sum":
            values = grouped[column].sum(min_count=1).rename("metric_value").reset_index()
        elif aggregation == "mean":
            values = grouped[column].mean().rename("metric_value").reset_index()
        elif aggregation == "sales_growth":
            growth = usable.loc[usable["previous_4q_average_sales"].gt(0)].copy()
            growth_grouped = growth.groupby(groups, observed=True, sort=False, dropna=False)
            values = growth_grouped.agg(
                current=("recent_4q_average_sales", "sum"),
                previous=("previous_4q_average_sales", "sum"),
            ).reset_index()
            values["metric_value"] = values["current"] / values["previous"] - 1
            values = values[[*groups, "metric_value"]]
        else:
            usable["_weight"] = usable["recent_store_count"].clip(lower=0).fillna(0)
            usable["_weighted"] = usable[column] * usable["_weight"]
            weighted = usable.groupby(groups, observed=True, sort=False, dropna=False).agg(
                weighted_sum=("_weighted", "sum"),
                weight_sum=("_weight", "sum"),
                fallback=(column, "mean"),
            ).reset_index()
            weighted["metric_value"] = np.where(
                weighted["weight_sum"].gt(0),
                weighted["weighted_sum"] / weighted["weight_sum"],
                weighted["fallback"],
            )
            values = weighted[[*groups, "metric_value"]]
        return base.merge(values, on=groups, how="inner", validate="one_to_one")

    @staticmethod
    def _serialize_row(
        row: pd.Series,
        group_by: LookupGroup,
        unit: str,
        rank: int,
        distribution: dict[str, Any],
    ) -> dict[str, Any]:
        if group_by == "area":
            entity_code = str(row["area_code"])
            entity_name = str(row["area_name"])
        elif group_by == "industry":
            entity_code = str(row["industry_code"])
            entity_name = str(row["industry_name"])
        elif group_by == "district":
            entity_code = None
            entity_name = str(row["district_name"])
        else:
            entity_code = None
            entity_name = str(row["admin_dong_name"])
        value = float(row["metric_value"])
        difference_from_mean = value - float(distribution["mean"])
        difference_from_median = value - float(distribution["median"])
        standard_deviation = float(distribution["standard_deviation"])
        standard_deviation_distance = (
            difference_from_mean / standard_deviation if standard_deviation > 0 else 0.0
        )
        digits = 6 if unit == "ratio" else 2
        return {
            "rank": rank,
            "entity_code": entity_code,
            "entity_name": entity_name,
            "metric_value": round(value, digits),
            "metric_display_value": MarketLookupService._format_value(value, unit),
            "difference_from_mean": round(difference_from_mean, digits),
            "difference_from_mean_display": MarketLookupService._format_signed_value(
                difference_from_mean, unit,
            ),
            "difference_from_median": round(difference_from_median, digits),
            "difference_from_median_display": MarketLookupService._format_signed_value(
                difference_from_median, unit,
            ),
            "standard_deviation_distance": round(standard_deviation_distance, 2),
            "district_name": str(row["district_name"]) if "district_name" in row else None,
            "admin_dong_name": str(row["admin_dong_name"]) if "admin_dong_name" in row else None,
            "area_count": int(row["area_count"]),
            "observation_count": int(row["observation_count"]),
        }

    @staticmethod
    def _distribution(values: pd.Series, unit: str) -> dict[str, Any]:
        mean = float(values.mean())
        median = float(values.median())
        standard_deviation = float(values.std(ddof=0))
        return {
            "population_count": int(values.count()),
            "mean": mean,
            "mean_display": MarketLookupService._format_value(mean, unit),
            "median": median,
            "median_display": MarketLookupService._format_value(median, unit),
            "standard_deviation": standard_deviation,
            "standard_deviation_display": MarketLookupService._format_spread_value(
                standard_deviation, unit,
            ),
        }

    @staticmethod
    def _format_value(value: float, unit: str) -> str:
        if unit == "krw":
            return f"{value:,.0f}원"
        if unit == "ratio":
            return f"{value * 100:.1f}%"
        if unit == "count":
            return f"{value:,.0f}개"
        if unit == "count_per_sqkm":
            return f"{value:,.1f}개/㎢"
        return f"{value:,.0f}명"

    @staticmethod
    def _format_signed_value(value: float, unit: str) -> str:
        sign = "+" if value > 0 else ""
        if unit == "krw":
            return f"{sign}{value:,.0f}원"
        if unit == "ratio":
            return f"{sign}{value * 100:.1f}%p"
        if unit == "count":
            return f"{sign}{value:,.0f}개"
        if unit == "count_per_sqkm":
            return f"{sign}{value:,.1f}개/㎢"
        return f"{sign}{value:,.0f}명"

    @staticmethod
    def _format_spread_value(value: float, unit: str) -> str:
        if unit == "ratio":
            return f"{value * 100:.1f}%p"
        return MarketLookupService._format_value(value, unit)
