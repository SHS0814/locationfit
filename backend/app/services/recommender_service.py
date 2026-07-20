from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.services.artifact_loader import load_artifacts
from backend.recommender import AreaRecommender, RecommendationRequest
from src.models.area_recommender import RecommendationResult


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
    def __init__(self, artifact_dir: Path) -> None:
        bundle = load_artifacts(artifact_dir)
        self.manifest = bundle.manifest
        self.index = bundle.recommendation_index
        self.evidence = bundle.evidence
        self.engine = AreaRecommender(self.index, self.evidence)
        self.location_lookup = self.index.set_index("area_code")[
            ["latitude", "longitude", "admin_dong_name"]
        ].to_dict(orient="index")

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
        }

    def _run_recommendation(self, payload: RecommendationRequestSchema) -> RecommendationResult:
        values = payload.model_dump()
        for field in (
            "preferred_area_types", "target_age_groups", "preferred_time_bands",
            "preferred_districts", "excluded_districts",
        ):
            values[field] = tuple(values[field])
        request = RecommendationRequest(**values)
        return self.engine.recommend(request)

    def _serialize_recommendations(self, result: RecommendationResult) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in result.recommendations.to_dict(orient="records"):
            location = self.location_lookup[str(row["area_code"])]
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
                "final_score": round(float(row["final_score"]), 2),
                "condition_fit_score": round(float(row["condition_fit_score"]), 2),
                "raw_evidence_score": _json_safe(row["raw_evidence_score"]),
                "reliability_adjusted_evidence_score": _json_safe(row["reliability_adjusted_evidence_score"]),
                "data_reliability": float(row["data_reliability"]),
                "reliability_grade": str(row["reliability_grade"]),
                "positive_reasons": json.loads(row["positive_reasons"]),
                "negative_reasons": json.loads(row["negative_reasons"]),
                "evidence_summary": _json_safe(json.loads(row["evidence_summary"])),
                "warnings": json.loads(row["warning_messages"]),
            })
        return items

    def recommend(self, payload: RecommendationRequestSchema) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        result = self._run_recommendation(payload)
        items = self._serialize_recommendations(result)
        return items, _json_safe(result.diagnostics)

    def recommend_with_report(
        self,
        payload: RecommendationRequestSchema,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        """Return ranked items and a top-three report against the full eligible population."""
        result = self._run_recommendation(payload)
        items = self._serialize_recommendations(result)
        return items, _json_safe(result.diagnostics), self._build_recommendation_report(result, items)

    def _build_recommendation_report(
        self,
        result: RecommendationResult,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        eligible = result.eligible_candidates.copy()

        def metric_values(row: dict[str, Any]) -> dict[str, Any]:
            return _json_safe({metric: row.get(metric) for metric in REPORT_METRICS})

        benchmark: dict[str, Any] = {}
        for metric in REPORT_METRICS:
            values = pd.to_numeric(eligible.get(metric), errors="coerce").dropna()
            benchmark[metric] = float(values.median()) if not values.empty else None
        benchmark = _json_safe(benchmark)

        eligible_lookup = {
            str(row["area_code"]): row
            for row in eligible.to_dict(orient="records")
        }
        areas: list[dict[str, Any]] = []
        for item in items[:3]:
            source = eligible_lookup[str(item["area_code"])]
            metrics = metric_values(source)
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
                "metrics": metrics,
                "benchmark_delta": delta,
                "positive_reasons": item["positive_reasons"],
                "negative_reasons": item["negative_reasons"],
                "warnings": item["warnings"],
            }))

        data_period = self.manifest.get("data_period", {})
        performance_period = str(data_period.get("performance", ""))
        competition_reference_period = performance_period.rsplit("~", 1)[-1] or "최근 관측 분기"
        return {
            "candidate_count": len(eligible),
            "benchmark_label": "동일 조건 전체 후보 중앙값",
            "data_period": data_period,
            "competition_reference_period": competition_reference_period,
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
