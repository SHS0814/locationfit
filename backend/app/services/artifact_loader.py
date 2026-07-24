from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry import shape


INDEX_FILE = "area_recommendation_index.parquet"
EVIDENCE_FILE = "area_industry_evidence.parquet"
BOUNDARIES_FILE = "area_boundaries.parquet"
DISTRICT_BOUNDARIES_FILE = "district_boundaries.parquet"


@dataclass(frozen=True)
class ArtifactBundle:
    recommendation_index: pd.DataFrame
    evidence: pd.DataFrame
    boundaries: dict[str, dict[str, Any]]
    district_boundaries: dict[str, dict[str, Any]]
    manifest: dict


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_artifacts(artifact_dir: Path) -> ArtifactBundle:
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"아티팩트 manifest를 찾을 수 없습니다: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = {
        name: artifact_dir / name
        for name in (INDEX_FILE, EVIDENCE_FILE, BOUNDARIES_FILE, DISTRICT_BOUNDARIES_FILE)
    }
    for name, path in paths.items():
        if not path.exists():
            raise RuntimeError(f"추천 아티팩트를 찾을 수 없습니다: {path}")
        expected = manifest.get("files", {}).get(name, {}).get("sha256")
        if expected and _sha256(path) != expected:
            raise RuntimeError(f"추천 아티팩트 체크섬이 일치하지 않습니다: {name}")

    index = pd.read_parquet(paths[INDEX_FILE])
    evidence = pd.read_parquet(paths[EVIDENCE_FILE])
    boundary_frame = pd.read_parquet(paths[BOUNDARIES_FILE])
    district_boundary_frame = pd.read_parquet(paths[DISTRICT_BOUNDARIES_FILE])
    index_required = {
        "area_code", "area_name", "district_name", "admin_dong_name",
        "area_type_code", "area_type_name", "latitude", "longitude", "data_reliability",
    }
    evidence_required = {
        "area_code", "industry_code", "industry_name", "data_reliability",
        "reliability_grade", "stale_observation_flag",
    }
    missing_index = sorted(index_required - set(index.columns))
    missing_evidence = sorted(evidence_required - set(evidence.columns))
    missing_boundaries = sorted({"area_code", "geometry"} - set(boundary_frame.columns))
    missing_district_boundaries = sorted(
        {"district_code", "district_name", "geometry"} - set(district_boundary_frame.columns)
    )
    if missing_index or missing_evidence or missing_boundaries or missing_district_boundaries:
        raise RuntimeError(
            "추천 아티팩트 스키마가 올바르지 않습니다. "
            f"index={missing_index}, evidence={missing_evidence}, boundaries={missing_boundaries}, "
            f"district_boundaries={missing_district_boundaries}"
        )
    if not index["latitude"].between(37.0, 38.0).all() or not index["longitude"].between(126.0, 128.0).all():
        raise RuntimeError("추천 아티팩트 좌표가 서울 범위를 벗어났습니다.")
    boundary_frame["area_code"] = boundary_frame["area_code"].astype(str)
    if boundary_frame["area_code"].duplicated().any():
        raise RuntimeError("상권 경계 아티팩트에 area_code 중복이 있습니다.")
    index_codes = set(index["area_code"].astype(str))
    boundary_codes = set(boundary_frame["area_code"])
    if index_codes != boundary_codes:
        raise RuntimeError("추천 인덱스와 상권 경계의 area_code가 일치하지 않습니다.")

    boundaries: dict[str, dict[str, Any]] = {}
    for row in boundary_frame.itertuples(index=False):
        geometry = json.loads(row.geometry)
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise RuntimeError(f"지원하지 않는 상권 경계 형식입니다: {geometry.get('type')}")
        boundaries[str(row.area_code)] = geometry

    district_boundary_frame["district_code"] = district_boundary_frame["district_code"].astype(str)
    district_boundary_frame["district_name"] = district_boundary_frame["district_name"].astype(str)
    if district_boundary_frame["district_code"].duplicated().any() or district_boundary_frame["district_name"].duplicated().any():
        raise RuntimeError("자치구 경계 아티팩트에 코드 또는 이름 중복이 있습니다.")
    expected_districts = set(index["district_name"].dropna().astype(str))
    if len(district_boundary_frame) != 25 or set(district_boundary_frame["district_name"]) != expected_districts:
        raise RuntimeError("추천 인덱스와 서울 25개 자치구 경계가 일치하지 않습니다.")
    district_boundaries: dict[str, dict[str, Any]] = {}
    for row in district_boundary_frame.itertuples(index=False):
        geometry = json.loads(row.geometry)
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise RuntimeError(f"지원하지 않는 자치구 경계 형식입니다: {geometry.get('type')}")
        polygon = shape(geometry)
        min_x, min_y, max_x, max_y = polygon.bounds
        if polygon.is_empty or not polygon.is_valid:
            raise RuntimeError(f"비어 있거나 유효하지 않은 자치구 경계입니다: {row.district_name}")
        if not (
            126.0 < min_x < 128.0 and 126.0 < max_x < 128.0
            and 37.0 < min_y < 38.0 and 37.0 < max_y < 38.0
        ):
            raise RuntimeError(f"서울 범위를 벗어난 자치구 경계입니다: {row.district_name}")
        district_boundaries[str(row.district_name)] = {
            "district_code": str(row.district_code),
            "geometry": geometry,
        }
    return ArtifactBundle(index, evidence, boundaries, district_boundaries, manifest)
