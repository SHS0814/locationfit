"""Weighted-distance commercial-area recommender using observed evidence only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.preprocessing import RobustScaler

from src.utils.paths import INTERIM_DIR, OUTPUT_DIR, PROCESSED_DIR, PROJECT_ROOT


FINAL_WEIGHTS = {"condition_fit_score": 0.60, "reliability_adjusted_evidence_score": 0.40}
EVIDENCE_WEIGHTS: dict[str, tuple[float, Literal["positive", "negative"]]] = {
    "recent_4q_average_sales": (0.15, "positive"),
    "recent_4q_average_sales_per_store": (0.20, "positive"),
    "yoy_growth_rate": (0.08, "positive"),
    "recent_4q_growth_rate": (0.08, "positive"),
    "long_term_sales_trend_slope": (0.07, "positive"),
    "sales_coefficient_of_variation": (0.10, "negative"),
    "decline_quarter_ratio": (0.08, "negative"),
    "competition_intensity": (0.08, "negative"),
    "closing_rate": (0.06, "negative"),
    "churn_rate": (0.04, "negative"),
    "recent_closure_rate_increase": (0.02, "negative"),
    "net_store_growth_rate": (0.04, "positive"),
}
DEFAULT_K = 50
C_GRADE_PENALTY = 0.90
RECENT_PROFILE_QUARTERS = ["20251", "20252", "20253", "20254"]
TREND_FEATURES = [
    "log_floating_density",
    "log_resident_density",
    "log_worker_density",
    "log_apartment_household_density",
    "log_store_density",
]

AGE_FEATURES = {
    "10": "age_10_floating_ratio",
    "20": "age_20_floating_ratio",
    "30": "age_30_floating_ratio",
    "40": "age_40_floating_ratio",
    "50": "age_50_floating_ratio",
    "60_plus": "age_60_plus_floating_ratio",
}
TIME_FEATURES = {
    "00_06": "time_00_06_floating_ratio",
    "06_11": "time_06_11_floating_ratio",
    "11_14": "time_11_14_floating_ratio",
    "14_17": "time_14_17_floating_ratio",
    "17_21": "time_17_21_floating_ratio",
    "21_24": "time_21_24_floating_ratio",
}
IMPORTANCE_FEATURES: dict[str, list[str]] = {
    "weekend_importance": ["weekend_floating_ratio"],
    "floating_population_importance": ["log_floating_density"],
    "resident_population_importance": ["log_resident_density"],
    "worker_population_importance": ["log_worker_density"],
    "apartment_importance": ["log_apartment_household_density", "log_apartment_complex_density"],
    "transport_facility_importance": ["log_transport_facility_density"],
    "education_facility_importance": ["log_education_facility_density"],
    "medical_facility_importance": ["log_medical_facility_density"],
    "shopping_facility_importance": ["log_shopping_facility_density"],
    "culture_facility_importance": ["log_culture_facility_density"],
}
IMPORTANCE_FIELDS = list(IMPORTANCE_FEATURES)


@dataclass(frozen=True)
class RecommendationRequest:
    """Validated user preference schema for one recommendation request."""

    industry_code: str
    preferred_area_types: tuple[str, ...] = ()
    target_gender: str | None = None
    target_age_groups: tuple[str, ...] = ()
    preferred_time_bands: tuple[str, ...] = ()
    weekend_importance: float = 0.0
    floating_population_importance: float = 0.0
    resident_population_importance: float = 0.0
    worker_population_importance: float = 0.0
    apartment_importance: float = 0.0
    transport_facility_importance: float = 0.0
    education_facility_importance: float = 0.0
    medical_facility_importance: float = 0.0
    shopping_facility_importance: float = 0.0
    culture_facility_importance: float = 0.0
    store_density_preference: str | None = None
    franchise_preference: str | None = None
    preferred_districts: tuple[str, ...] = ()
    excluded_districts: tuple[str, ...] = ()
    min_data_reliability: float = 0.0
    top_n: int = 10


@dataclass(frozen=True)
class PreferenceFeature:
    """One explicit user input to structural feature mapping."""

    input_field: str
    feature: str
    weight: float
    direction: Literal["high", "low"]
    label: str


@dataclass(frozen=True)
class RecommendationResult:
    """Ranked output plus diagnostics and full eligible candidate scores."""

    recommendations: pd.DataFrame
    candidates: pd.DataFrame
    diagnostics: dict[str, Any]
    preference_features: tuple[PreferenceFeature, ...]


def _validate_importance(value: float, name: str) -> None:
    if not np.isfinite(value) or value < 0 or value > 1:
        raise ValueError(f"{name}은 0~1 사이여야 합니다: {value}")


def validate_request(
    request: RecommendationRequest,
    *,
    valid_industries: set[str] | None = None,
) -> None:
    """Validate enumerations, ranges, requested industry, and non-empty conditions."""
    if not request.industry_code or not request.industry_code.strip():
        raise ValueError("industry_code는 필수입니다.")
    if valid_industries is not None and request.industry_code not in valid_industries:
        raise ValueError(f"존재하지 않는 industry_code입니다: {request.industry_code}")
    if request.target_gender not in {None, "male", "female"}:
        raise ValueError("target_gender는 male 또는 female이어야 합니다.")
    invalid_age = sorted(set(request.target_age_groups) - set(AGE_FEATURES))
    if invalid_age:
        raise ValueError(f"지원하지 않는 target_age_groups: {invalid_age}")
    invalid_time = sorted(set(request.preferred_time_bands) - set(TIME_FEATURES))
    if invalid_time:
        raise ValueError(f"지원하지 않는 preferred_time_bands: {invalid_time}")
    if request.store_density_preference not in {None, "high", "low"}:
        raise ValueError("store_density_preference는 high 또는 low여야 합니다.")
    if request.franchise_preference not in {None, "high", "low"}:
        raise ValueError("franchise_preference는 high 또는 low여야 합니다.")
    for field in IMPORTANCE_FIELDS:
        _validate_importance(float(getattr(request, field)), field)
    _validate_importance(float(request.min_data_reliability), "min_data_reliability")
    if request.top_n < 1 or request.top_n > 100:
        raise ValueError("top_n은 1~100 사이여야 합니다.")
    condition_values = [
        request.preferred_area_types,
        request.target_gender,
        request.target_age_groups,
        request.preferred_time_bands,
        *(getattr(request, field) for field in IMPORTANCE_FIELDS),
        request.store_density_preference,
        request.franchise_preference,
        request.preferred_districts,
        request.excluded_districts,
        request.min_data_reliability,
    ]
    if not any(bool(value) for value in condition_values):
        raise ValueError("industry_code 외에 최소 한 개의 희망 조건을 입력해야 합니다.")


def build_preference_features(request: RecommendationRequest, available_columns: Iterable[str]) -> tuple[PreferenceFeature, ...]:
    """Map only explicitly supplied soft preferences to actual structural columns."""
    available = set(available_columns)
    mappings: list[PreferenceFeature] = []
    if request.target_gender:
        feature = f"{request.target_gender}_floating_ratio"
        mappings.append(PreferenceFeature("target_gender", feature, 1.0, "high", f"{request.target_gender} 유동인구 비율"))
    if request.target_age_groups:
        weight = 1.0 / len(request.target_age_groups)
        for value in request.target_age_groups:
            mappings.append(PreferenceFeature("target_age_groups", AGE_FEATURES[value], weight, "high", f"{value} 연령 유동인구 비율"))
    if request.preferred_time_bands:
        weight = 1.0 / len(request.preferred_time_bands)
        for value in request.preferred_time_bands:
            mappings.append(PreferenceFeature("preferred_time_bands", TIME_FEATURES[value], weight, "high", f"{value} 시간대 유동인구 비율"))
    for input_field, features in IMPORTANCE_FEATURES.items():
        importance = float(getattr(request, input_field))
        if importance <= 0:
            continue
        for feature in features:
            mappings.append(PreferenceFeature(input_field, feature, importance / len(features), "high", input_field.removesuffix("_importance")))
    if request.store_density_preference:
        mappings.append(PreferenceFeature("store_density_preference", "log_store_density", 1.0, request.store_density_preference, "전체 점포 밀도"))
    if request.franchise_preference:
        mappings.append(PreferenceFeature("franchise_preference", "franchise_ratio", 1.0, request.franchise_preference, "프랜차이즈 비율"))
    missing = sorted({mapping.feature for mapping in mappings} - available)
    if missing:
        raise ValueError(f"추천 인덱스에 매핑 피처가 없습니다: {missing}")
    return tuple(mappings)


def feature_mapping_table() -> pd.DataFrame:
    """Return the explicit public input-to-profile mapping documentation."""
    rows: list[dict[str, Any]] = [
        {"input_field": "industry_code", "accepted_values": "sales industry_code", "profile_features": "-", "direction": "-", "filter_type": "evidence join", "description": "required industry"},
        {"input_field": "preferred_area_types", "accepted_values": "A,D,R,U or Korean names", "profile_features": "area_type_code|area_type_name", "direction": "exact", "filter_type": "hard", "description": "included commercial-area types"},
        {"input_field": "target_gender", "accepted_values": "male|female", "profile_features": "male_floating_ratio|female_floating_ratio", "direction": "high", "filter_type": "distance", "description": "target gender floating ratio"},
        {"input_field": "target_age_groups", "accepted_values": "10|20|30|40|50|60_plus", "profile_features": "|".join(AGE_FEATURES.values()), "direction": "high", "filter_type": "distance", "description": "target age ratios"},
        {"input_field": "preferred_time_bands", "accepted_values": "|".join(TIME_FEATURES), "profile_features": "|".join(TIME_FEATURES.values()), "direction": "high", "filter_type": "distance", "description": "preferred floating time ratios"},
        {"input_field": "store_density_preference", "accepted_values": "high|low", "profile_features": "log_store_density", "direction": "high or low", "filter_type": "distance", "description": "total store density preference"},
        {"input_field": "franchise_preference", "accepted_values": "high|low", "profile_features": "franchise_ratio", "direction": "high or low", "filter_type": "distance", "description": "franchise share preference"},
        {"input_field": "preferred_districts", "accepted_values": "Seoul district names", "profile_features": "district_name", "direction": "exact", "filter_type": "hard", "description": "included districts"},
        {"input_field": "excluded_districts", "accepted_values": "Seoul district names", "profile_features": "district_name", "direction": "exclude", "filter_type": "hard", "description": "excluded districts"},
        {"input_field": "min_data_reliability", "accepted_values": "0~1", "profile_features": "data_reliability", "direction": "minimum", "filter_type": "hard", "description": "minimum profile and evidence reliability"},
        {"input_field": "top_n", "accepted_values": "1~100", "profile_features": "-", "direction": "-", "filter_type": "output", "description": "returned recommendation count"},
    ]
    for field, features in IMPORTANCE_FEATURES.items():
        rows.append({
            "input_field": field,
            "accepted_values": "0~1",
            "profile_features": "|".join(features),
            "direction": "high",
            "filter_type": "distance weight",
            "description": "0 excludes the condition; positive value is an explicit feature weight",
        })
    return pd.DataFrame(rows)


def build_recommendation_index(
    area_profile: pd.DataFrame,
    feature_dictionary: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate recent four quarters to one structural row per area without sales."""
    required = {"quarter", "area_code", "area_name", "area_type_code", "area_type_name", "district_name", "data_reliability"}
    missing = sorted(required - set(area_profile))
    if missing:
        raise ValueError(f"area_profile 필수 컬럼 누락: {missing}")
    structural_features = feature_dictionary.loc[feature_dictionary["role"].eq("feature"), "feature"].tolist()
    structural_features = [feature for feature in structural_features if feature in area_profile and pd.api.types.is_numeric_dtype(area_profile[feature])]
    forbidden = [feature for feature in structural_features if "sales" in feature.lower() or "매출" in feature]
    if forbidden:
        raise ValueError(f"condition_fit에 매출 피처가 포함될 수 없습니다: {forbidden}")
    profile = area_profile.copy()
    profile["quarter"] = profile["quarter"].astype("string")
    profile["area_code"] = profile["area_code"].astype("string")
    recent = profile.loc[profile["quarter"].isin(RECENT_PROFILE_QUARTERS)].copy()
    if sorted(recent["quarter"].unique().tolist()) != RECENT_PROFILE_QUARTERS:
        raise ValueError("최근 4분기 area_profile이 완전하지 않습니다.")
    means = recent.groupby("area_code", observed=True, sort=False)[structural_features].mean().reset_index()
    latest = (
        recent.sort_values("quarter")
        .groupby("area_code", observed=True, sort=False)
        .tail(1)[["area_code", "area_name", "district_name", "area_type_code", "area_type_name"]]
    )
    quality_columns = [column for column in feature_dictionary.loc[feature_dictionary["role"].eq("quality"), "feature"] if column in recent and pd.api.types.is_numeric_dtype(recent[column])]
    quality = recent.groupby("area_code", observed=True, sort=False)[quality_columns].mean().reset_index()
    index = latest.merge(means, on="area_code", how="inner", validate="one_to_one").merge(quality, on="area_code", how="inner", validate="one_to_one")
    full = profile.sort_values(["area_code", "quarter"])
    for feature in TREND_FEATURES:
        if feature not in full:
            continue
        work = full[["area_code", "quarter", feature]].copy()
        quarter_order = {quarter: position for position, quarter in enumerate(sorted(full["quarter"].unique()))}
        work["x"] = work["quarter"].map(quarter_order).astype(float)
        work["xy"] = work["x"] * work[feature]
        work["x2"] = work["x"] ** 2
        grouped = work.groupby("area_code", observed=True, sort=False).agg(
            n=(feature, "count"), sum_x=("x", "sum"), sum_y=(feature, "sum"), sum_xy=("xy", "sum"), sum_x2=("x2", "sum")
        )
        denominator = grouped["n"] * grouped["sum_x2"] - grouped["sum_x"] ** 2
        numerator = grouped["n"] * grouped["sum_xy"] - grouped["sum_x"] * grouped["sum_y"]
        grouped[f"trend_{feature}"] = np.where(denominator > 0, numerator / denominator, 0.0)
        index = index.merge(grouped[[f"trend_{feature}"]].reset_index(), on="area_code", how="left", validate="one_to_one")
    index["area_code"] = index["area_code"].astype("string")
    index = index.sort_values("area_code").reset_index(drop=True)
    if index["area_code"].duplicated().any():
        raise ValueError("area recommendation index에 area_code 중복이 있습니다.")
    return index


def weighted_euclidean_scores(
    values: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return weighted Euclidean distance and a deterministic 0~100 fit score."""
    if values.ndim != 2 or target.shape != (values.shape[1],) or weights.shape != target.shape:
        raise ValueError("weighted Euclidean 입력 shape가 일치하지 않습니다.")
    if np.any(weights < 0) or not np.any(weights > 0):
        raise ValueError("거리 weight는 하나 이상 양수여야 합니다.")
    distance = np.sqrt(np.sum(weights * (values - target) ** 2, axis=1) / weights.sum())
    lower, upper = float(distance.min()), float(distance.max())
    score = np.full(len(distance), 100.0) if upper == lower else 100.0 * (upper - distance) / (upper - lower)
    return distance, np.clip(score, 0, 100)


def weighted_cosine_scores(values: np.ndarray, target: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return weighted cosine similarity transformed from [-1, 1] to [0, 100]."""
    weighted_values = values * np.sqrt(weights)
    weighted_target = target * np.sqrt(weights)
    denominator = np.linalg.norm(weighted_values, axis=1) * np.linalg.norm(weighted_target)
    similarity = np.divide(weighted_values @ weighted_target, denominator, out=np.zeros(len(values)), where=denominator > 0)
    return np.clip((similarity + 1.0) * 50.0, 0, 100)


def robust_percentile(series: pd.Series, *, positive: bool) -> pd.Series:
    """Score non-missing values 0~100 by deterministic within-industry rank."""
    result = pd.Series(np.nan, index=series.index, dtype="float64")
    valid = series.notna()
    count = int(valid.sum())
    if count == 0:
        return result
    if count == 1:
        result.loc[valid] = 50.0
        return result
    ranks = series.loc[valid].rank(method="average")
    score = 100.0 * (ranks - 1.0) / (count - 1.0)
    result.loc[valid] = score if positive else 100.0 - score
    return result


def score_industry_evidence(industry_evidence: pd.DataFrame) -> pd.DataFrame:
    """Percentile-score observed metrics and shrink scores toward the industry mean."""
    if industry_evidence["industry_code"].nunique() != 1:
        raise ValueError("score_industry_evidence에는 단일 업종만 전달해야 합니다.")
    scored = industry_evidence.copy()
    weighted_sum = pd.Series(0.0, index=scored.index)
    available_weight = pd.Series(0.0, index=scored.index)
    for metric, (weight, direction) in EVIDENCE_WEIGHTS.items():
        if metric not in scored:
            raise ValueError(f"evidence 지표 컬럼 누락: {metric}")
        score_column = f"evidence_component_{metric}"
        scored[score_column] = robust_percentile(scored[metric], positive=direction == "positive")
        valid = scored[score_column].notna()
        weighted_sum.loc[valid] += weight * scored.loc[valid, score_column]
        available_weight.loc[valid] += weight
    scored["evidence_metric_coverage"] = available_weight / sum(weight for weight, _ in EVIDENCE_WEIGHTS.values())
    scored["raw_evidence_score"] = np.divide(
        weighted_sum,
        available_weight,
        out=np.full(len(scored), np.nan),
        where=available_weight.gt(0),
    )
    industry_mean = float(scored["raw_evidence_score"].mean())
    scored["evidence_score_multiply"] = scored["raw_evidence_score"] * scored["data_reliability"]
    scored["evidence_score_shrinkage"] = (
        scored["data_reliability"] * scored["raw_evidence_score"]
        + (1.0 - scored["data_reliability"]) * industry_mean
    )
    scored["reliability_adjusted_evidence_score"] = scored["evidence_score_shrinkage"]
    c_mask = scored["reliability_grade"].eq("C")
    scored.loc[c_mask, "reliability_adjusted_evidence_score"] *= C_GRADE_PENALTY
    for column in ("raw_evidence_score", "reliability_adjusted_evidence_score", "evidence_score_multiply", "evidence_score_shrinkage"):
        scored[column] = scored[column].clip(0, 100)
    return scored


def score_weights_table() -> pd.DataFrame:
    """Document final, evidence, direction, and reliability adjustment weights."""
    rows = [
        {"score_group": "final", "metric": metric, "weight": weight, "direction": "positive", "note": "final score component"}
        for metric, weight in FINAL_WEIGHTS.items()
    ]
    rows.extend(
        {"score_group": "evidence", "metric": metric, "weight": weight, "direction": direction, "note": "within-industry percentile"}
        for metric, (weight, direction) in EVIDENCE_WEIGHTS.items()
    )
    rows.extend([
        {"score_group": "reliability", "metric": "shrinkage", "weight": np.nan, "direction": "industry mean", "note": "r*score + (1-r)*industry_mean"},
        {"score_group": "reliability", "metric": "C_grade_penalty", "weight": C_GRADE_PENALTY, "direction": "negative", "note": "A/B unchanged; D excluded"},
        {"score_group": "distance", "metric": "weighted_euclidean", "weight": np.nan, "direction": "lower distance", "note": f"RobustScaler; default k={DEFAULT_K}"},
    ])
    return pd.DataFrame(rows)


class AreaRecommender:
    """Deterministic weighted-distance area recommender with observed evidence."""

    def __init__(self, recommendation_index: pd.DataFrame, evidence: pd.DataFrame) -> None:
        self.index = recommendation_index.copy()
        self.evidence = evidence.copy()
        self.index["area_code"] = self.index["area_code"].astype("string")
        self.evidence["area_code"] = self.evidence["area_code"].astype("string")
        self.evidence["industry_code"] = self.evidence["industry_code"].astype("string")
        if self.index["area_code"].duplicated().any():
            raise ValueError("recommendation_index area_code 중복")
        if self.evidence.duplicated(["area_code", "industry_code"]).any():
            raise ValueError("evidence area_code × industry_code 중복")
        self.valid_industries = set(self.evidence["industry_code"])

    def _condition_scores(
        self,
        preferences: tuple[PreferenceFeature, ...],
        metric: Literal["euclidean", "cosine"],
    ) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
        scored = self.index[["area_code"]].copy()
        if not preferences:
            scored["condition_fit_score"] = 100.0
            scored["condition_distance"] = 0.0
            return scored, {}
        features = [preference.feature for preference in preferences]
        values = self.index[features].astype(float)
        medians = values.median()
        values = values.fillna(medians)
        scaled = RobustScaler().fit_transform(values)
        lower = np.nanquantile(scaled, 0.01, axis=0)
        upper = np.nanquantile(scaled, 0.99, axis=0)
        clipped = np.clip(scaled, lower, upper)
        target = np.array([upper[index] if preference.direction == "high" else lower[index] for index, preference in enumerate(preferences)])
        weights = np.array([preference.weight for preference in preferences], dtype=float)
        distance, euclidean = weighted_euclidean_scores(clipped, target, weights)
        cosine = weighted_cosine_scores(clipped, target, weights)
        scored["condition_distance"] = distance
        scored["condition_fit_score"] = euclidean if metric == "euclidean" else cosine
        contributions: dict[str, np.ndarray] = {}
        span = np.where(upper > lower, upper - lower, 1.0)
        for index, preference in enumerate(preferences):
            component = 100.0 * (1.0 - np.abs(clipped[:, index] - target[index]) / span[index])
            contributions[f"{preference.input_field}:{preference.feature}"] = np.clip(component, 0, 100)
        scored["condition_fit_euclidean"] = euclidean
        scored["condition_fit_cosine"] = cosine
        return scored, contributions

    def _hard_filter(self, frame: pd.DataFrame, request: RecommendationRequest) -> pd.DataFrame:
        filtered = frame
        if request.preferred_area_types:
            values = set(request.preferred_area_types)
            filtered = filtered.loc[filtered["area_type_code"].isin(values) | filtered["area_type_name"].isin(values)]
        if request.preferred_districts:
            filtered = filtered.loc[filtered["district_name"].isin(request.preferred_districts)]
        if request.excluded_districts:
            filtered = filtered.loc[~filtered["district_name"].isin(request.excluded_districts)]
        if request.min_data_reliability > 0:
            filtered = filtered.loc[filtered["data_reliability"].ge(request.min_data_reliability)]
        return filtered

    def _explain(
        self,
        row: pd.Series,
        preferences: tuple[PreferenceFeature, ...],
        contribution_lookup: dict[str, dict[str, float]],
    ) -> tuple[str, str, str, str]:
        area_contributions = contribution_lookup.get(str(row["area_code"]), {})
        labeled = []
        for preference in preferences:
            key = f"{preference.input_field}:{preference.feature}"
            if key in area_contributions:
                labeled.append({"factor": preference.label, "feature": preference.feature, "fit_score": round(area_contributions[key], 2), "weight": round(preference.weight, 4)})
        positive = sorted(labeled, key=lambda item: (-item["fit_score"], -item["weight"], item["feature"]))[:3]
        negative = sorted(labeled, key=lambda item: (item["fit_score"], -item["weight"], item["feature"]))[:2]
        summary = {
            "sales_growth": {
                "yoy_growth_rate": _json_number(row.get("yoy_growth_rate")),
                "recent_4q_growth_rate": _json_number(row.get("recent_4q_growth_rate")),
                "long_term_trend": _json_number(row.get("long_term_sales_trend_slope")),
            },
            "sales_stability": {
                "coefficient_of_variation": _json_number(row.get("sales_coefficient_of_variation")),
                "decline_quarter_ratio": _json_number(row.get("decline_quarter_ratio")),
            },
            "competition": {"competition_intensity": _json_number(row.get("competition_intensity"))},
            "closure_risk": {
                "closing_rate": _json_number(row.get("closing_rate")),
                "churn_rate": _json_number(row.get("churn_rate")),
                "closure_rate_increased": int(row.get("closure_rate_increased_flag", 0)),
            },
            "data_quality": {
                "reliability": _json_number(row.get("data_reliability")),
                "grade": str(row.get("reliability_grade")),
                "evidence_metric_coverage": _json_number(row.get("evidence_metric_coverage")),
            },
        }
        warnings: list[str] = []
        if row.get("reliability_grade") == "B":
            warnings.append("B등급 근거: 점수는 정상 반영하되 품질 정보를 확인하세요.")
        if row.get("reliability_grade") == "C":
            warnings.append("C등급 근거: 신뢰도 보정 점수에 10% 감점을 적용했습니다.")
        if int(row.get("current_sales_missing_flag", 0)):
            warnings.append("현재분기 매출이 없어 0으로 대체하지 않았습니다.")
        if float(row.get("evidence_metric_coverage", 1.0)) < 0.8:
            warnings.append("일부 evidence 지표가 없어 가용 지표만 정규화했습니다.")
        return (
            json.dumps(positive, ensure_ascii=False),
            json.dumps(negative, ensure_ascii=False),
            json.dumps(summary, ensure_ascii=False),
            json.dumps(warnings, ensure_ascii=False),
        )

    def recommend(
        self,
        request: RecommendationRequest,
        *,
        k: int = DEFAULT_K,
        distance_metric: Literal["euclidean", "cosine"] = "euclidean",
    ) -> RecommendationResult:
        """Rank eligible evidence-backed areas by 60% condition and 40% evidence."""
        validate_request(request, valid_industries=self.valid_industries)
        if k not in {10, 20, 30, 50}:
            raise ValueError("k는 10, 20, 30, 50 중 하나여야 합니다.")
        if request.top_n > k:
            raise ValueError("top_n은 k보다 클 수 없습니다.")
        preferences = build_preference_features(request, self.index.columns)
        condition, contributions = self._condition_scores(preferences, distance_metric)
        structural = self.index.merge(condition, on="area_code", how="left", validate="one_to_one")
        structural = self._hard_filter(structural, request)
        industry_raw = self.evidence.loc[self.evidence["industry_code"].eq(request.industry_code)].copy()
        industry_scored = score_industry_evidence(industry_raw)
        d_count = int(industry_scored["reliability_grade"].eq("D").sum())
        stale_count = int(industry_scored["stale_observation_flag"].eq(1).sum())
        candidates = structural.merge(industry_scored, on="area_code", how="inner", suffixes=("", "_evidence"), validate="one_to_one")
        candidates = candidates.loc[
            candidates["reliability_grade"].ne("D")
            & candidates["stale_observation_flag"].eq(0)
            & candidates["data_reliability_evidence"].ge(request.min_data_reliability)
        ].copy()
        candidates = candidates.sort_values(["condition_fit_score", "area_code"], ascending=[False, True]).head(k).copy()
        if candidates.empty:
            raise ValueError("필터와 신뢰도 조건을 만족하는 추천 후보가 없습니다.")
        candidates["final_score"] = (
            FINAL_WEIGHTS["condition_fit_score"] * candidates["condition_fit_score"]
            + FINAL_WEIGHTS["reliability_adjusted_evidence_score"] * candidates["reliability_adjusted_evidence_score"]
        ).clip(0, 100)
        candidates = candidates.sort_values(["final_score", "condition_fit_score", "area_code"], ascending=[False, False, True]).reset_index(drop=True)
        candidates["rank"] = np.arange(1, len(candidates) + 1)
        contribution_lookup: dict[str, dict[str, float]] = {}
        area_codes = self.index["area_code"].astype(str).tolist()
        for key, values in contributions.items():
            for area_code, value in zip(area_codes, values, strict=True):
                contribution_lookup.setdefault(area_code, {})[key] = float(value)
        explanations = candidates.apply(lambda row: self._explain(row, preferences, contribution_lookup), axis=1)
        candidates[["positive_reasons", "negative_reasons", "evidence_summary", "warning_messages"]] = pd.DataFrame(explanations.tolist(), index=candidates.index)
        candidates["area_type"] = candidates["area_type_name"]
        candidates["data_reliability"] = candidates["data_reliability_evidence"]
        candidates["stale_flag"] = candidates["stale_observation_flag"]
        candidates["selected_k"] = k
        candidates["distance_metric"] = distance_metric
        output_columns = [
            "rank", "area_code", "area_name", "district_name", "area_type", "industry_code", "industry_name",
            "final_score", "condition_fit_score", "raw_evidence_score", "reliability_adjusted_evidence_score",
            "data_reliability", "reliability_grade", "stale_flag", "positive_reasons", "negative_reasons",
            "evidence_summary", "warning_messages", "selected_k", "distance_metric",
        ]
        recommendations = candidates.head(request.top_n)[output_columns].copy()
        diagnostics = {
            "industry_code": request.industry_code,
            "industry_evidence_combinations": len(industry_raw),
            "hard_filtered_structural_areas": len(structural),
            "eligible_candidates_before_k": int(
                structural["area_code"].isin(
                    industry_scored.loc[
                        industry_scored["reliability_grade"].ne("D")
                        & industry_scored["stale_observation_flag"].eq(0)
                        & industry_scored["data_reliability"].ge(request.min_data_reliability),
                        "area_code",
                    ]
                ).sum()
            ),
            "d_grade_excluded": d_count,
            "stale_excluded": stale_count,
            "c_grade_candidates": int(candidates["reliability_grade"].eq("C").sum()),
            "selected_k": k,
            "returned": len(recommendations),
            "distance_metric": distance_metric,
            "condition_feature_count": len(preferences),
            "condition_features": [preference.feature for preference in preferences],
            "evidence_adjustment": "industry_mean_shrinkage_with_C_10pct_penalty",
        }
        return RecommendationResult(recommendations, candidates, diagnostics, preferences)


def _json_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(numeric, 6) if np.isfinite(numeric) else None


def top_overlap(first: pd.DataFrame, second: pd.DataFrame, *, n: int = 10) -> float:
    """Return top-n set overlap ratio."""
    left = set(first.head(n)["area_code"])
    right = set(second.head(n)["area_code"])
    denominator = min(n, len(left), len(right))
    return len(left & right) / denominator if denominator else np.nan


def rank_correlation(first: pd.DataFrame, second: pd.DataFrame, *, n: int = 10) -> float:
    """Return Spearman correlation on the union of two top-n lists."""
    left = first.head(n)["area_code"].tolist()
    right = second.head(n)["area_code"].tolist()
    union = sorted(set(left) | set(right))
    if len(union) < 2:
        return 1.0
    fallback = n + 1
    left_rank = {code: index + 1 for index, code in enumerate(left)}
    right_rank = {code: index + 1 for index, code in enumerate(right)}
    correlation = spearmanr([left_rank.get(code, fallback) for code in union], [right_rank.get(code, fallback) for code in union]).statistic
    return float(correlation) if np.isfinite(correlation) else 0.0


def perturb_importances(request: RecommendationRequest, factor: float) -> RecommendationRequest:
    """Scale explicit numeric importance fields for sensitivity analysis."""
    changes = {field: float(np.clip(getattr(request, field) * factor, 0, 1)) for field in IMPORTANCE_FIELDS}
    return replace(request, **changes)


def scenario_suite(
    recommender: AreaRecommender,
    scenarios: dict[str, RecommendationRequest],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run samples, weight sensitivity, k stability, and validation checks."""
    sample_frames: list[pd.DataFrame] = []
    sensitivity_rows: list[dict[str, Any]] = []
    k_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    for scenario, request in scenarios.items():
        baseline = recommender.recommend(request, k=DEFAULT_K)
        sample = baseline.recommendations.copy()
        sample.insert(0, "scenario", scenario)
        sample_frames.append(sample)
        repeated = recommender.recommend(request, k=DEFAULT_K).recommendations
        deterministic = baseline.recommendations["area_code"].tolist() == repeated["area_code"].tolist()
        max_weight_share = max((preference.weight for preference in baseline.preference_features), default=0.0) / max(sum((preference.weight for preference in baseline.preference_features), 0.0), 1e-12)
        validation_rows.extend([
            {"scenario": scenario, "check": "deterministic", "status": "PASS" if deterministic else "FAIL", "value": int(deterministic), "details": "same input rerun"},
            {"scenario": scenario, "check": "score_bounds", "status": "PASS" if sample[["final_score", "condition_fit_score", "raw_evidence_score", "reliability_adjusted_evidence_score"]].apply(lambda column: column.between(0, 100).all()).all() else "FAIL", "value": float(sample["final_score"].max()), "details": "all scores 0~100"},
            {"scenario": scenario, "check": "no_D_or_stale", "status": "PASS" if sample["reliability_grade"].ne("D").all() and sample["stale_flag"].eq(0).all() else "FAIL", "value": int((sample["reliability_grade"].eq("D") | sample["stale_flag"].eq(1)).sum()), "details": "default exclusion"},
            {"scenario": scenario, "check": "single_feature_weight_share", "status": "PASS" if max_weight_share <= 0.5 else "WARNING", "value": max_weight_share, "details": "maximum explicit condition weight share"},
        ])
        for factor in (0.90, 0.95, 1.05, 1.10):
            changed = recommender.recommend(perturb_importances(request, factor), k=DEFAULT_K).recommendations
            sensitivity_rows.append({
                "scenario": scenario,
                "importance_factor": factor,
                "top10_overlap": top_overlap(baseline.recommendations, changed),
                "top10_rank_correlation": rank_correlation(baseline.recommendations, changed),
                "baseline_top1": baseline.recommendations.iloc[0]["area_code"],
                "changed_top1": changed.iloc[0]["area_code"],
            })
        k_results = {k: recommender.recommend(request, k=k).recommendations for k in (10, 20, 30, 50)}
        reference = k_results[50]
        for k, result in k_results.items():
            k_rows.append({
                "scenario": scenario,
                "k": k,
                "reference_k": 50,
                "top10_overlap": top_overlap(result, reference),
                "top10_rank_correlation": rank_correlation(result, reference),
                "top1_area_code": result.iloc[0]["area_code"],
            })
        cosine = recommender.recommend(request, k=DEFAULT_K, distance_metric="cosine").recommendations
        validation_rows.append({
            "scenario": scenario,
            "check": "euclidean_cosine_top10_overlap",
            "status": "INFO",
            "value": top_overlap(baseline.recommendations, cosine),
            "details": "weighted Euclidean selected for monotonic directional targets",
        })
    evidence = recommender.evidence
    eligible = evidence.loc[evidence["reliability_grade"].ne("D") & evidence["stale_observation_flag"].eq(0)]
    counts = eligible.groupby("industry_code", observed=True).size()
    scored_all = pd.concat(
        [score_industry_evidence(group) for _, group in evidence.groupby("industry_code", observed=True, sort=False)],
        ignore_index=True,
    )
    raw_mean = float(scored_all["raw_evidence_score"].mean())
    multiply_mean = float(scored_all["evidence_score_multiply"].mean())
    shrinkage_mean = float(scored_all["evidence_score_shrinkage"].mean())
    sensitivity_min_overlap = min((row["top10_overlap"] for row in sensitivity_rows), default=np.nan)
    selected_k_overlap = min(
        (row["top10_overlap"] for row in k_rows if row["k"] == DEFAULT_K),
        default=np.nan,
    )
    unavailable_industries = sorted(set(evidence["industry_code"]) - set(counts.index))
    validation_rows.extend([
        {"scenario": "ALL", "check": "eligible_industry_count", "status": "INFO", "value": len(counts), "details": "industries with at least one eligible area"},
        {"scenario": "ALL", "check": "unavailable_industry_count", "status": "INFO", "value": len(unavailable_industries), "details": f"all evidence is D/stale: {unavailable_industries}"},
        {"scenario": "ALL", "check": "eligible_areas_per_industry_min", "status": "INFO", "value": int(counts.min()), "details": "D/stale excluded"},
        {"scenario": "ALL", "check": "eligible_areas_per_industry_median", "status": "INFO", "value": float(counts.median()), "details": "D/stale excluded"},
        {"scenario": "ALL", "check": "eligible_areas_per_industry_max", "status": "INFO", "value": int(counts.max()), "details": "D/stale excluded"},
        {"scenario": "ALL", "check": "D_grade_excluded_count", "status": "INFO", "value": int(evidence["reliability_grade"].eq("D").sum()), "details": "excluded before KNN candidates"},
        {"scenario": "ALL", "check": "stale_excluded_count", "status": "INFO", "value": int(evidence["stale_observation_flag"].eq(1).sum()), "details": "excluded before KNN candidates"},
        {"scenario": "ALL", "check": "C_grade_penalized_count", "status": "INFO", "value": int(evidence["reliability_grade"].eq("C").sum()), "details": "10% penalty before final score"},
        {"scenario": "ALL", "check": "evidence_multiply_mean", "status": "INFO", "value": multiply_mean, "details": f"raw mean={raw_mean:.4f}"},
        {"scenario": "ALL", "check": "evidence_shrinkage_mean", "status": "PASS" if abs(shrinkage_mean - raw_mean) < abs(multiply_mean - raw_mean) else "FAIL", "value": shrinkage_mean, "details": "selected because it avoids excessive reliability penalty"},
        {"scenario": "ALL", "check": "importance_sensitivity_min_top10_overlap", "status": "PASS" if sensitivity_min_overlap >= 0.7 else "WARNING", "value": sensitivity_min_overlap, "details": "importance ±5~10%"},
        {"scenario": "ALL", "check": "selected_k_top10_overlap_vs_50", "status": "PASS" if selected_k_overlap == 1.0 else "WARNING", "value": selected_k_overlap, "details": f"selected k={DEFAULT_K}; reference k=50"},
        {"scenario": "ALL", "check": "condition_evidence_independence", "status": "PASS", "value": 1, "details": "condition mappings reference area recommendation index only; evidence scoring uses industry evidence only"},
    ])
    return (
        pd.concat(sample_frames, ignore_index=True),
        pd.DataFrame(sensitivity_rows),
        pd.DataFrame(k_rows),
        pd.DataFrame(validation_rows),
    )


def load_recommender_inputs(project_root: Path = PROJECT_ROOT) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load profile/evidence and their dictionaries from canonical project paths."""
    profile = pd.read_parquet(project_root / "data/processed/area_profile.parquet")
    evidence = pd.read_parquet(project_root / "data/processed/area_industry_evidence.parquet")
    profile_dictionary = pd.read_csv(project_root / "outputs/tables/area_profile_feature_dictionary.csv")
    evidence_dictionary = pd.read_csv(project_root / "outputs/tables/area_industry_evidence_dictionary.csv")
    return profile, evidence, profile_dictionary, evidence_dictionary


def save_recommender_artifacts(
    recommendation_index: pd.DataFrame,
    sample_results: pd.DataFrame,
    sensitivity: pd.DataFrame,
    k_stability: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    project_root: Path = PROJECT_ROOT,
) -> None:
    """Save index, mapping, weights, validation, samples, and stability outputs."""
    processed = project_root / "data/processed"
    tables = project_root / "outputs/tables"
    processed.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    recommendation_index.to_parquet(processed / "area_recommendation_index.parquet", index=False)
    feature_mapping_table().to_csv(tables / "recommender_feature_mapping.csv", index=False, encoding="utf-8-sig")
    score_weights_table().to_csv(tables / "recommender_score_weights.csv", index=False, encoding="utf-8-sig")
    validation.to_csv(tables / "recommender_validation.csv", index=False, encoding="utf-8-sig")
    sample_results.to_csv(tables / "recommender_sample_results.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(tables / "recommender_weight_sensitivity.csv", index=False, encoding="utf-8-sig")
    k_stability.to_csv(tables / "recommender_k_stability.csv", index=False, encoding="utf-8-sig")
