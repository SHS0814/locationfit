from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.services.artifact_loader import load_artifacts
from backend.recommender import AreaRecommender, RecommendationRequest


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

    def recommend(self, payload: RecommendationRequestSchema) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        values = payload.model_dump()
        for field in (
            "preferred_area_types", "target_age_groups", "preferred_time_bands",
            "preferred_districts", "excluded_districts",
        ):
            values[field] = tuple(values[field])
        request = RecommendationRequest(**values)
        result = self.engine.recommend(request)
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
        return items, _json_safe(result.diagnostics)
