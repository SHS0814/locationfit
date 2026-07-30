from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.services.artifact_loader import load_artifacts
from backend.app.services.cost_provider import (
    CommercialCostProvider,
    UnavailableCostProvider,
    calculate_budget_fit,
)
from backend.app.services.market_lookup_service import (
    LookupGroup,
    LookupMetric,
    LookupOrder,
    MarketLookupService,
)
from backend.recommender import AreaRecommender, RecommendationRequest
from src.models.area_recommender import STRATEGY_GROUP_WEIGHTS, RecommendationResult

AGE_OPTIONS = [
    {"code": "10", "name": "10대"}, {"code": "20", "name": "20대"},
    {"code": "30", "name": "30대"}, {"code": "40", "name": "40대"},
    {"code": "50", "name": "50대"}, {"code": "60_plus", "name": "60대 이상"},
]
TIME_OPTIONS = [
    {"code": "00_06", "name": "00~06시"}, {"code": "06_11", "name": "06~11시"},
    {"code": "11_14", "name": "11~14시"}, {"code": "14_17", "name": "14~17시"},
    {"code": "17_21", "name": "17~21시"}, {"code": "21_24", "name": "21~24시"},
]
DEFAULT_RENT_REFERENCE = {
    "rentable_area_sqm": 33.05785,
    "floor": "f1",
}

REPORT_METRICS = (
    "final_score",
    "condition_fit_score",
    "reliability_adjusted_evidence_score",
    "recent_4q_average_sales",
    "recent_4q_growth_rate",
    "recent_store_count",
    "same_industry_store_density",
    "closing_rate",
    "floating_population",
    "resident_population",
    "worker_population",
    "data_reliability",
    "estimated_converted_monthly_rent_krw",
    "unit_converted_rent_krw_sqm",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class RecommenderService:
    def __init__(
        self,
        artifact_dir: Path,
        cost_provider: CommercialCostProvider | None = None,
    ) -> None:
        bundle = load_artifacts(artifact_dir)
        self.manifest = bundle.manifest
        self.index = bundle.recommendation_index
        self.evidence = bundle.evidence
        self.boundaries = bundle.boundaries
        self.district_boundaries = bundle.district_boundaries
        self.engine = AreaRecommender(self.index, self.evidence)
        self.cost_provider = cost_provider or UnavailableCostProvider()
        self.market_lookup = MarketLookupService(
            self.index,
            self.evidence,
            self.manifest.get("data_period", {}),
        )
        self.location_lookup = self.index.set_index("area_code")[
            ["latitude", "longitude", "admin_dong_name", "area_size_sqm"]
        ].to_dict(orient="index")
        self.area_name_lookup = self.index.set_index(self.index["area_code"].astype(str))[
            "area_name"
        ].astype(str).to_dict()

    @property
    def artifact_version(self) -> str:
        return str(self.manifest.get("artifact_version", "unknown"))

    def metadata(self) -> dict[str, Any]:
        industries = (
            self.evidence[["industry_code", "industry_name"]]
            .drop_duplicates()
            .sort_values(["industry_name", "industry_code"])
        )
        area_types = (
            self.index[["area_type_code", "area_type_name"]]
            .drop_duplicates()
            .sort_values("area_type_code")
        )
        return {
            "artifact_version": self.artifact_version,
            "data_period": self.manifest.get("data_period", {}),
            "industries": [
                {"code": str(row.industry_code), "name": str(row.industry_name)}
                for row in industries.itertuples(index=False)
            ],
            "districts": sorted(self.index["district_name"].dropna().astype(str).unique().tolist()),
            "area_types": [
                {"code": str(row.area_type_code), "name": str(row.area_type_name)}
                for row in area_types.itertuples(index=False)
            ],
            "age_groups": AGE_OPTIONS,
            "time_bands": TIME_OPTIONS,
            "rent_floors": self.cost_provider.options(),
            "performance_weight_presets": {
                "balanced": dict(STRATEGY_GROUP_WEIGHTS["balanced"]),
                "growth_focused": dict(STRATEGY_GROUP_WEIGHTS["growth"]),
                "stability_focused": dict(STRATEGY_GROUP_WEIGHTS["stability"]),
            },
        }

    def market_geographies(
        self,
        *,
        group_by: str,
        entity_keys: list[str],
    ) -> list[dict[str, Any]]:
        if group_by == "area":
            unknown = [key for key in entity_keys if key not in self.boundaries]
            if unknown:
                raise ValueError(f"지원하지 않는 상권 코드입니다: {', '.join(unknown)}")
            return [
                {
                    "entity_key": key,
                    "entity_name": self.area_name_lookup[key],
                    "boundary": self.boundaries[key],
                }
                for key in entity_keys
            ]
        if group_by == "district":
            unknown = [key for key in entity_keys if key not in self.district_boundaries]
            if unknown:
                raise ValueError(f"지원하지 않는 자치구입니다: {', '.join(unknown)}")
            return [
                {
                    "entity_key": key,
                    "entity_name": key,
                    "boundary": self.district_boundaries[key]["geometry"],
                }
                for key in entity_keys
            ]
        raise ValueError(f"지도에서 지원하지 않는 조회 단위입니다: {group_by}")

    def recommendation_evidence_context(
        self,
        payload: RecommendationRequestSchema,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """Describe provenance and scoring without exposing raw artifacts."""
        periods = self.manifest.get("data_period", {})
        return {
            "artifact_version": self.artifact_version,
            "data_period": periods,
            "sources": [
                {"metrics": "상권 경계", "name": "서울시 상권분석서비스(영역-상권)", "dataset_id": "OA-15560"},
                {"metrics": "추정매출·성장률", "name": "서울시 상권분석서비스(추정매출-상권)", "dataset_id": "OA-15572"},
                {"metrics": "점포 수·폐업률", "name": "서울시 상권분석서비스(점포-상권)", "dataset_id": "OA-15577"},
                {"metrics": "유동인구", "name": "서울시 상권분석서비스(길단위인구-상권)", "dataset_id": "OA-15568"},
                {"metrics": "상주인구", "name": "서울시 상권분석서비스(상주인구-상권)", "dataset_id": "OA-15584"},
                {"metrics": "직장인구", "name": "서울시 상권분석서비스(직장인구-상권)", "dataset_id": "OA-15569"},
                {
                    "metrics": "환산임대료",
                    "name": self.manifest.get(
                        "commercial_rent_source",
                        "서울시 상권분석서비스 임대시세",
                    ),
                    "dataset_id": None,
                },
            ],
            "metric_definitions": {
                "recent_4q_average_sales": "최근 4개 분기의 분기 추정매출 평균",
                "recent_4q_growth_rate": "최근 4개 분기와 직전 4개 분기의 추정매출 변화율",
                "recent_store_count": "최신 관측 분기의 선택 업종 점포 수",
                "same_industry_store_density": "상권 면적 1㎢당 선택 업종 점포 수",
                "closing_rate": "관측 점포 데이터의 폐업률",
                "population_metrics": "최근 관측 분기들의 상권별 평균 인구",
                "estimated_converted_monthly_rent_krw": "행정동 임대시세에 입력 면적을 적용한 월 환산임대료 추정치",
            },
            "scoring": {
                "strategy": payload.strategy,
                "final_weights": diagnostics.get("final_weights", {}),
                "evidence_group_weights": diagnostics.get("evidence_group_weights", {}),
                "performance_group_weights": diagnostics.get("performance_group_weights", {}),
                "performance_weights_source": diagnostics.get("performance_weights_source"),
                "condition_fit": "사용자가 지정한 고객·시간·입지 특성과 상권 구조의 가중 거리 기반 적합도",
                "performance_evidence": "동일 업종 내 관측 성과를 백분위화한 뒤 데이터 신뢰도에 따라 업종 평균 쪽으로 보정",
                "budget_adjustment": (
                    "기존 종합점수 80%와 임대예산 적합도 20%를 결합"
                    if diagnostics.get("budget_adjusted") else
                    "임대예산에 따른 순위 재조정 없음"
                ),
                "benchmark": "현재 필터를 통과한 동일 조건 전체 후보의 중앙값",
            },
            "limitations": [
                "매출은 관측된 추정매출이며 실제 개별 점포 매출이나 미래 매출 예측이 아닙니다.",
                "추천 점수는 후보 간 비교용 모델 점수이며 성공 확률이 아닙니다.",
                "환산임대료는 관리비·부가가치세를 제외한 추정치입니다.",
                "추천 상담 중에는 배포 아티팩트를 사용하며 서울시 원천 API를 실시간 조회하지 않습니다.",
            ],
        }

    def lookup_market_rankings(
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
        return self.market_lookup.rank(
            group_by=group_by,
            metric=metric,
            top_n=top_n,
            order=order,
            district_name=district_name,
            admin_dong_name=admin_dong_name,
            industry_code=industry_code,
        )

    def _run_recommendation(self, payload: RecommendationRequestSchema) -> RecommendationResult:
        values = payload.model_dump(exclude={
            "total_startup_budget_krw", "monthly_converted_rent_limit_krw",
            "rentable_area_sqm", "floor",
        })
        for field in (
            "preferred_area_types", "target_age_groups", "preferred_time_bands",
            "preferred_districts", "excluded_districts",
        ):
            values[field] = tuple(values[field])
        request = RecommendationRequest(**values)
        result = self.engine.recommend(request)
        return self._apply_budget_ranking(result, payload)

    def _estimate(self, area_code: str, payload: RecommendationRequestSchema):
        if (
            payload.rentable_area_sqm is None
            or payload.floor is None
        ):
            return None
        return self.cost_provider.estimate(
            area_code,
            payload.floor,
            payload.rentable_area_sqm,
        )

    def _apply_budget_ranking(
        self,
        result: RecommendationResult,
        payload: RecommendationRequestSchema,
    ) -> RecommendationResult:
        """Rerank the deterministic engine's candidate pool only when a rent cap is usable."""
        if payload.monthly_converted_rent_limit_krw is None:
            return result
        candidates = result.candidates.copy()
        estimates = {
            str(area_code): self._estimate(str(area_code), payload)
            for area_code in candidates["area_code"]
        }
        if not any(estimate is not None for estimate in estimates.values()):
            diagnostics = {
                **result.diagnostics,
                "budget_adjusted": False,
                "budget_adjustment_reason": "commercial_cost_unavailable",
            }
            return replace(result, diagnostics=diagnostics)
        candidates["base_final_score"] = candidates["final_score"].astype(float)
        candidates["budget_fit_score"] = candidates["area_code"].astype(str).map(
            lambda code: (
                calculate_budget_fit(
                    float(payload.monthly_converted_rent_limit_krw),
                    estimates[code].estimated_converted_monthly_rent_krw,
                )
                if estimates.get(code) is not None else 0.0
            )
        )
        candidates["final_score"] = (
            candidates["base_final_score"] * 0.8 + candidates["budget_fit_score"] * 0.2
        ).clip(0, 100)
        candidates = candidates.sort_values(
            ["final_score", "condition_fit_score", "area_code"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        candidates["rank"] = range(1, len(candidates) + 1)
        recommendations = candidates.head(payload.top_n)[result.recommendations.columns].copy()
        diagnostics = {
            **result.diagnostics,
            "returned": len(recommendations),
            "budget_adjusted": True,
            "budget_weight": 0.2,
            "base_score_weight": 0.8,
            "rent_estimate_coverage": sum(value is not None for value in estimates.values()),
        }
        return replace(
            result,
            recommendations=recommendations,
            candidates=candidates,
            diagnostics=diagnostics,
        )

    def _serialize_recommendations(
        self,
        result: RecommendationResult,
        payload: RecommendationRequestSchema,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in result.recommendations.to_dict(orient="records"):
            location = self.location_lookup[str(row["area_code"])]
            candidate = result.candidates.loc[
                result.candidates["area_code"].astype(str).eq(str(row["area_code"]))
            ].iloc[0]
            estimate = self._estimate(str(row["area_code"]), payload)
            items.append({
                "rank": int(row["rank"]),
                "area_code": str(row["area_code"]),
                "area_name": str(row["area_name"]),
                "district_name": str(row["district_name"]),
                "admin_dong_name": _json_safe(location["admin_dong_name"]),
                "area_type": str(row["area_type"]),
                "industry_code": str(row["industry_code"]),
                "industry_name": str(row["industry_name"]),
                "latitude": float(location["latitude"]),
                "longitude": float(location["longitude"]),
                "area_size_sqm": float(location["area_size_sqm"]),
                "boundary": self.boundaries[str(row["area_code"])],
                "final_score": round(float(row["final_score"]), 2),
                "base_final_score": (
                    round(float(candidate["base_final_score"]), 2)
                    if "base_final_score" in candidate and pd.notna(candidate["base_final_score"])
                    else None
                ),
                "budget_fit_score": (
                    round(float(candidate["budget_fit_score"]), 2)
                    if "budget_fit_score" in candidate and pd.notna(candidate["budget_fit_score"])
                    else None
                ),
                "budget_adjusted": bool(result.diagnostics.get("budget_adjusted", False)),
                "condition_fit_score": round(float(row["condition_fit_score"]), 2),
                "raw_evidence_score": _json_safe(row["raw_evidence_score"]),
                "reliability_adjusted_evidence_score": _json_safe(row["reliability_adjusted_evidence_score"]),
                "data_reliability": float(row["data_reliability"]),
                "reliability_grade": str(row["reliability_grade"]),
                "positive_reasons": json.loads(row["positive_reasons"]),
                "negative_reasons": json.loads(row["negative_reasons"]),
                "evidence_summary": _json_safe(json.loads(row["evidence_summary"])),
                "performance_breakdown": _json_safe(row["performance_breakdown"]),
                "warnings": json.loads(row["warning_messages"]),
                "rental_estimate": estimate.to_dict() if estimate is not None else None,
            })
        return items

    def recommend(self, payload: RecommendationRequestSchema) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        result = self._run_recommendation(payload)
        items = self._serialize_recommendations(result, payload)
        return items, _json_safe(result.diagnostics)

    def recommend_with_report(
        self,
        payload: RecommendationRequestSchema,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        """Return ranked items and a top-three report against the full eligible population."""
        result = self._run_recommendation(payload)
        items = self._serialize_recommendations(result, payload)
        return (
            items,
            _json_safe(result.diagnostics),
            self._build_recommendation_report(result, items, payload),
        )

    def _build_recommendation_report(
        self,
        result: RecommendationResult,
        items: list[dict[str, Any]],
        payload: RecommendationRequestSchema,
    ) -> dict[str, Any]:
        eligible = result.eligible_candidates.copy()
        has_rent_conditions = all((
            payload.rentable_area_sqm is not None,
            payload.floor is not None,
        ))
        rental_payload = payload if has_rent_conditions else payload.model_copy(
            update=DEFAULT_RENT_REFERENCE
        )
        rental_area_sqm = rental_payload.rentable_area_sqm
        if rental_area_sqm is None:
            raise RuntimeError("임대료 보고서의 기준 면적이 설정되지 않았습니다.")
        rental_basis = (
            f"입력 조건 · {float(rental_area_sqm):g}㎡ · "
            f"{rental_payload.floor}"
            if has_rent_conditions
            else "기본 참고값 · 1층 · 10평(33.1㎡)"
        )

        def metric_values(row: dict[str, Any]) -> dict[str, Any]:
            return _json_safe({metric: row.get(metric) for metric in REPORT_METRICS})

        benchmark: dict[str, Any] = {}
        for metric in REPORT_METRICS:
            source = eligible[metric] if metric in eligible else pd.Series(dtype="float64")
            values = pd.to_numeric(source, errors="coerce").dropna()
            benchmark[metric] = float(values.median()) if not values.empty else None
        rental_estimates = {
            str(area_code): self._estimate(str(area_code), rental_payload)
            for area_code in eligible["area_code"].astype(str)
        }
        monthly_values = [
            estimate.estimated_converted_monthly_rent_krw
            for estimate in rental_estimates.values() if estimate is not None
        ]
        unit_values = [
            estimate.unit_converted_rent_krw_sqm
            for estimate in rental_estimates.values() if estimate is not None
        ]
        benchmark["estimated_converted_monthly_rent_krw"] = (
            float(pd.Series(monthly_values).median()) if monthly_values else None
        )
        benchmark["unit_converted_rent_krw_sqm"] = (
            float(pd.Series(unit_values).median()) if unit_values else None
        )
        benchmark = _json_safe(benchmark)

        eligible_lookup = {
            str(row["area_code"]): row
            for row in eligible.to_dict(orient="records")
        }
        areas: list[dict[str, Any]] = []
        for item in items[:3]:
            source = eligible_lookup[str(item["area_code"])]
            metrics = metric_values(source)
            estimate = rental_estimates.get(str(item["area_code"]))
            rental_estimate = estimate.to_dict() if estimate is not None else None
            if rental_estimate:
                metrics["estimated_converted_monthly_rent_krw"] = rental_estimate.get(
                    "estimated_converted_monthly_rent_krw"
                )
                metrics["unit_converted_rent_krw_sqm"] = rental_estimate.get(
                    "unit_converted_rent_krw_sqm"
                )
            # Keep public recommendation scores byte-for-byte aligned with the result cards.
            for score in (
                "final_score",
                "condition_fit_score",
                "reliability_adjusted_evidence_score",
            ):
                metrics[score] = item.get(score)
            delta = {
                metric: (
                    None
                    if metrics.get(metric) is None or benchmark.get(metric) is None
                    else float(metrics[metric]) - float(benchmark[metric])
                )
                for metric in REPORT_METRICS
            }
            areas.append(_json_safe({
                "rank": item["rank"],
                "area_code": item["area_code"],
                "area_name": item["area_name"],
                "district_name": item["district_name"],
                "area_type": item["area_type"],
                "reliability_grade": item["reliability_grade"],
                "base_final_score": item.get("base_final_score"),
                "budget_fit_score": item.get("budget_fit_score"),
                "rental_estimate": rental_estimate,
                "metrics": metrics,
                "benchmark_delta": delta,
                "positive_reasons": item["positive_reasons"],
                "negative_reasons": item["negative_reasons"],
                "warnings": item["warnings"],
                "performance_breakdown": item["performance_breakdown"],
            }))

        data_period = self.manifest.get("data_period", {})
        performance_period = str(data_period.get("performance", ""))
        competition_reference_period = performance_period.rsplit("~", 1)[-1] or "최근 관측 분기"
        return {
            "candidate_count": len(eligible),
            "benchmark_label": "동일 조건 전체 후보 중앙값",
            "data_period": data_period,
            "competition_reference_period": competition_reference_period,
            "rental_estimate_basis": rental_basis,
            "rental_estimate_uses_default": not has_rent_conditions,
            "performance_group_weights": result.diagnostics["performance_group_weights"],
            "performance_weights_source": result.diagnostics["performance_weights_source"],
            "benchmark": benchmark,
            "areas": areas,
        }

    def inspect_market_landscape(self, payload: RecommendationRequestSchema) -> dict[str, Any]:
        """Return bounded aggregate facts for agent exploration without exposing raw tables."""
        evidence = self.evidence.loc[
            self.evidence["industry_code"].astype(str).eq(payload.industry_code)
            & self.evidence["reliability_grade"].ne("D")
            & self.evidence["stale_observation_flag"].eq(0)
            & self.evidence["data_reliability"].ge(payload.min_data_reliability)
        ].copy()
        profile = self.index.copy()
        if payload.preferred_districts:
            profile = profile.loc[profile["district_name"].isin(payload.preferred_districts)]
        if payload.excluded_districts:
            profile = profile.loc[~profile["district_name"].isin(payload.excluded_districts)]
        if payload.preferred_area_types:
            values = set(payload.preferred_area_types)
            profile = profile.loc[
                profile["area_type_code"].isin(values) | profile["area_type_name"].isin(values)
            ]
        eligible = profile[["area_code", "district_name", "area_type_name"]].merge(
            evidence,
            on="area_code",
            how="inner",
            suffixes=("_profile", "_evidence"),
            validate="one_to_one",
        )

        def distribution(column: str) -> dict[str, float | None]:
            source = eligible[column] if column in eligible else pd.Series(dtype="float64")
            values = pd.to_numeric(source, errors="coerce").dropna()
            if values.empty:
                return {"p25": None, "median": None, "p75": None}
            return {
                "p25": float(values.quantile(0.25)),
                "median": float(values.median()),
                "p75": float(values.quantile(0.75)),
            }

        district_counts = eligible["district_name"].value_counts().head(5)
        type_counts = eligible["area_type_name"].value_counts().head(5)
        return _json_safe({
            "industry_code": payload.industry_code,
            "eligible_area_count": len(eligible),
            "top_districts_by_coverage": [
                {"district_name": str(name), "area_count": int(count)}
                for name, count in district_counts.items()
            ],
            "area_type_coverage": [
                {"area_type": str(name), "area_count": int(count)}
                for name, count in type_counts.items()
            ],
            "metric_distribution": {
                "recent_4q_average_sales": distribution("recent_4q_average_sales"),
                "recent_4q_growth_rate": distribution("recent_4q_growth_rate"),
                "competition_intensity": distribution("competition_intensity"),
                "closing_rate": distribution("closing_rate"),
                "data_reliability": distribution("data_reliability"),
            },
            "data_period": self.manifest.get("data_period", {}),
        })

    def analyze_strategy_scenarios(
        self,
        payload: RecommendationRequestSchema,
        *,
        preview_count: int = 3,
    ) -> list[dict[str, Any]]:
        """Run the three versioned strategies against the same confirmed constraints."""
        labels = {
            "condition_fit": ("조건 충실형", "말씀하신 고객·시간·입지 조건과 가까운 후보를 우선합니다."),
            "growth": ("성장 기회형", "최근 성장과 장기 추세가 강한 후보에 더 무게를 둡니다."),
            "stability": ("안정성 우선형", "매출 변동과 하락·폐업 위험이 낮은 후보를 우선합니다."),
        }
        scenarios: list[dict[str, Any]] = []
        requested_count = min(5, max(preview_count, payload.top_n))
        for strategy, (title, description) in labels.items():
            selected_request = payload.model_copy(update={"strategy": strategy})
            analysis_request = selected_request.model_copy(update={"top_n": requested_count})
            try:
                recommendations, diagnostics = self.recommend(analysis_request)
            except ValueError as exc:
                recommendations = []
                diagnostics = {
                    "strategy": strategy,
                    "policy_version": "strategy-v1",
                    "eligible_candidates_before_k": 0,
                    "returned": 0,
                    "warning": str(exc),
                }
            scenarios.append({
                "id": strategy,
                "strategy": strategy,
                "title": title,
                "description": description,
                "request": selected_request.model_dump(),
                "candidate_count": int(diagnostics["eligible_candidates_before_k"]),
                "recommendations": recommendations[:preview_count],
                "diagnostics": diagnostics,
                "relaxed_fields": [],
            })
        return scenarios

    def diagnose_constraint_conflicts(
        self,
        payload: RecommendationRequestSchema,
        scenarios: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Describe measurable conflicts and safe hard-filter relaxation options."""
        tradeoffs: list[dict[str, Any]] = []
        base_count = min((scenario["candidate_count"] for scenario in scenarios), default=0)
        if base_count < payload.top_n:
            tradeoffs.append({
                "kind": "candidate_scarcity",
                "message": f"현재 조건을 모두 만족하는 후보가 {base_count}곳으로 요청한 {payload.top_n}곳보다 적습니다.",
                "severity": "warning",
            })

        low_factors: dict[str, float] = {}
        for scenario in scenarios:
            if not scenario["recommendations"]:
                continue
            for reason in scenario["recommendations"][0].get("negative_reasons", []):
                score = float(reason.get("fit_score", 100))
                if score < 40:
                    factor = str(reason.get("factor", reason.get("feature", "선호 조건")))
                    low_factors[factor] = min(low_factors.get(factor, 100), score)
        for factor, score in sorted(low_factors.items(), key=lambda item: item[1])[:2]:
            tradeoffs.append({
                "kind": "preference_conflict",
                "message": f"상위 후보도 ‘{factor}’ 적합도가 {score:.1f}점으로 낮아 다른 조건과 상충합니다.",
                "severity": "info",
            })

        for left_index, left in enumerate(scenarios):
            left_codes = {item["area_code"] for item in left["recommendations"][:5]}
            for right in scenarios[left_index + 1:]:
                right_codes = {item["area_code"] for item in right["recommendations"][:5]}
                denominator = min(len(left_codes), len(right_codes))
                overlap = len(left_codes & right_codes) / denominator if denominator else 1.0
                if overlap < 0.4:
                    tradeoffs.append({
                        "kind": "strategy_disagreement",
                        "message": f"{left['title']}과 {right['title']}의 상위 후보가 크게 달라 우선순위 선택이 중요합니다.",
                        "severity": "info",
                    })

        relaxations: list[dict[str, Any]] = []
        variants: list[tuple[str, dict[str, Any], str]] = []
        if payload.preferred_districts:
            variants.append(("preferred_districts", {"preferred_districts": []}, "선호 지역을 서울 전체로 확대"))
        if payload.preferred_area_types:
            variants.append(("preferred_area_types", {"preferred_area_types": []}, "상권 유형 제한을 해제"))
        if payload.preferred_districts and payload.preferred_area_types:
            variants.append((
                "preferred_districts,preferred_area_types",
                {"preferred_districts": [], "preferred_area_types": []},
                "선호 지역과 상권 유형을 모두 확대",
            ))
        for field, changes, label in variants:
            relaxed = payload.model_copy(update={**changes, "strategy": "condition_fit"})
            try:
                _, diagnostics = self.recommend(relaxed)
            except ValueError:
                continue
            count = int(diagnostics["eligible_candidates_before_k"])
            if count > base_count:
                relaxations.append({
                    "id": field,
                    "label": label,
                    "relaxed_fields": field.split(","),
                    "candidate_count_before": base_count,
                    "candidate_count_after": count,
                    "request": relaxed.model_dump(),
                })
        return tradeoffs, relaxations

    def compare(
        self,
        area_codes: list[str],
        industry_code: str,
        *,
        allowed_area_codes: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return observed comparison metrics for up to five eligible result areas."""
        requested = list(dict.fromkeys(str(code) for code in area_codes))
        if not requested or len(requested) > 5:
            raise ValueError("비교할 추천 상권을 1~5개 선택해주세요.")
        if allowed_area_codes is not None and not set(requested).issubset(allowed_area_codes):
            raise ValueError("현재 추천 결과에 포함된 상권만 비교할 수 있습니다.")

        profile_columns = [
            "area_code", "area_name", "district_name", "area_type_name",
            "floating_population", "resident_population", "worker_population",
            "transport_facility_count", "education_facility_count",
            "medical_facility_count", "shopping_facility_count", "culture_facility_count",
            "apartment_average_market_price", "data_reliability",
        ]
        evidence_columns = [
            "area_code", "competition_intensity", "recent_store_count",
            "same_industry_store_density", "recent_4q_average_sales",
            "recent_4q_growth_rate", "closing_rate", "data_reliability", "reliability_grade",
        ]
        profile = self.index.loc[self.index["area_code"].astype(str).isin(requested), profile_columns].copy()
        evidence = self.evidence.loc[
            self.evidence["area_code"].astype(str).isin(requested)
            & self.evidence["industry_code"].astype(str).eq(industry_code),
            evidence_columns,
        ].copy()
        evidence = evidence.rename(columns={"data_reliability": "evidence_data_reliability"})
        compared = profile.merge(evidence, on="area_code", how="left", validate="one_to_one")
        if set(compared["area_code"].astype(str)) != set(requested):
            raise ValueError("비교할 상권 데이터를 찾을 수 없습니다.")
        order = {code: index for index, code in enumerate(requested)}
        compared["_order"] = compared["area_code"].astype(str).map(order)
        compared = compared.sort_values("_order")

        rows: list[dict[str, Any]] = []
        for row in compared.to_dict(orient="records"):
            rows.append(_json_safe({
                "area_code": str(row["area_code"]),
                "area_name": str(row["area_name"]),
                "district_name": str(row["district_name"]),
                "area_type": str(row["area_type_name"]),
                "floating_population": row.get("floating_population"),
                "resident_population": row.get("resident_population"),
                "worker_population": row.get("worker_population"),
                "transport_facility_count": row.get("transport_facility_count"),
                "education_facility_count": row.get("education_facility_count"),
                "medical_facility_count": row.get("medical_facility_count"),
                "shopping_facility_count": row.get("shopping_facility_count"),
                "culture_facility_count": row.get("culture_facility_count"),
                "apartment_average_market_price": row.get("apartment_average_market_price"),
                "competition_intensity": row.get("competition_intensity"),
                "recent_store_count": row.get("recent_store_count"),
                "same_industry_store_density": row.get("same_industry_store_density"),
                "recent_4q_average_sales": row.get("recent_4q_average_sales"),
                "recent_4q_growth_rate": row.get("recent_4q_growth_rate"),
                "closing_rate": row.get("closing_rate"),
                "data_reliability": row.get("evidence_data_reliability", row.get("data_reliability")),
                "reliability_grade": row.get("reliability_grade"),
            }))
        return rows
