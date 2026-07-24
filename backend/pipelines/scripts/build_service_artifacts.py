from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely import make_valid, set_precision
from shapely.geometry import mapping


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = PROJECT_ROOT / "data/processed"
OUTPUT_DIR = PROJECT_ROOT / "backend/artifacts/current"
BOUNDARY_SOURCE_DIR = PROJECT_ROOT / "data/raw/area"
DISTRICT_BOUNDARY_SOURCE_DIR = PROJECT_ROOT / "data/raw/district"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rounded_coordinates(value):
    if isinstance(value, (list, tuple)):
        return [_rounded_coordinates(item) for item in value]
    return round(float(value), 6)


def build_area_boundaries(index: pd.DataFrame) -> pd.DataFrame:
    shape_files = sorted(BOUNDARY_SOURCE_DIR.glob("*.shp"))
    if len(shape_files) != 1:
        raise ValueError(
            "data/raw/area에 서울시 상권분석서비스(영역-상권) SHP 파일이 하나 필요합니다."
        )
    boundaries = gpd.read_file(shape_files[0])
    required = {"TRDAR_CD", "geometry"}
    missing = sorted(required - set(boundaries.columns))
    if missing:
        raise ValueError(f"상권 경계 SHP 필수 컬럼이 없습니다: {missing}")
    boundaries = boundaries[["TRDAR_CD", "geometry"]].rename(
        columns={"TRDAR_CD": "area_code"}
    )
    boundaries["area_code"] = boundaries["area_code"].astype(str)
    if boundaries["area_code"].duplicated().any():
        raise ValueError("상권 경계 SHP에 area_code 중복이 있습니다.")
    if not boundaries.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("상권 경계 SHP에 Polygon이 아닌 도형이 있습니다.")
    if set(boundaries["area_code"]) != set(index["area_code"].astype(str)):
        raise ValueError("추천 인덱스와 상권 경계 SHP의 area_code가 일치하지 않습니다.")

    boundaries = boundaries.to_crs("EPSG:4326")
    return pd.DataFrame({
        "area_code": boundaries["area_code"],
        "geometry": boundaries.geometry.map(
            lambda geometry: json.dumps(
                {
                    "type": geometry.geom_type,
                    "coordinates": _rounded_coordinates(mapping(geometry)["coordinates"]),
                },
                separators=(",", ":"),
            )
        ),
    }).sort_values("area_code").reset_index(drop=True)


def build_district_boundaries(index: pd.DataFrame, source_path: Path | None = None) -> pd.DataFrame:
    if source_path is None:
        source_files = sorted([
            *DISTRICT_BOUNDARY_SOURCE_DIR.glob("*.shp"),
            *DISTRICT_BOUNDARY_SOURCE_DIR.glob("*.geojson"),
            *DISTRICT_BOUNDARY_SOURCE_DIR.glob("*.json"),
        ])
        if len(source_files) != 1:
            raise ValueError(
                "data/raw/district에 서울 자치구 경계 SHP 또는 GeoJSON 파일이 하나 필요합니다."
            )
        source_path = source_files[0]

    boundaries = gpd.read_file(source_path)
    required = {"SIG_CD", "SIG_KOR_NM", "geometry"}
    missing = sorted(required - set(boundaries.columns))
    if missing:
        raise ValueError(f"자치구 경계 파일 필수 컬럼이 없습니다: {missing}")
    boundaries = boundaries[["SIG_CD", "SIG_KOR_NM", "geometry"]].rename(
        columns={"SIG_CD": "district_code", "SIG_KOR_NM": "district_name"}
    )
    boundaries["district_code"] = boundaries["district_code"].astype(str)
    boundaries["district_name"] = boundaries["district_name"].astype(str)
    expected_names = set(index["district_name"].dropna().astype(str))
    boundaries = boundaries.loc[boundaries["district_name"].isin(expected_names)].copy()
    if boundaries["district_name"].duplicated().any():
        raise ValueError("자치구 경계 파일에 district_name 중복이 있습니다.")
    if set(boundaries["district_name"]) != expected_names:
        missing_names = sorted(expected_names - set(boundaries["district_name"]))
        extra_names = sorted(set(boundaries["district_name"]) - expected_names)
        raise ValueError(
            f"추천 인덱스와 자치구 경계 이름이 일치하지 않습니다: missing={missing_names}, extra={extra_names}"
        )
    if len(boundaries) != 25:
        raise ValueError(f"서울 자치구 경계는 25개여야 합니다: {len(boundaries)}")
    if not boundaries.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("자치구 경계 파일에 Polygon이 아닌 도형이 있습니다.")
    invalid = ~boundaries.geometry.is_valid
    if invalid.any():
        boundaries.loc[invalid, "geometry"] = boundaries.loc[invalid, "geometry"].map(make_valid)
    if boundaries.geometry.is_empty.any() or not boundaries.geometry.is_valid.all():
        raise ValueError("자치구 경계 파일에 비어 있거나 유효하지 않은 도형이 있습니다.")
    if not boundaries.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("자치구 경계 복구 결과에 Polygon이 아닌 도형이 있습니다.")

    if boundaries.crs is None:
        raise ValueError("자치구 경계 파일의 좌표계 정보가 없습니다.")
    boundaries = boundaries.to_crs("EPSG:4326")
    boundaries["geometry"] = boundaries.geometry.map(
        lambda geometry: make_valid(set_precision(geometry, grid_size=0.000001))
    )
    if boundaries.geometry.is_empty.any() or not boundaries.geometry.is_valid.all():
        raise ValueError("좌표 정밀도 보정 후 유효하지 않은 자치구 경계가 있습니다.")
    if not boundaries.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("좌표 정밀도 보정 결과에 Polygon이 아닌 도형이 있습니다.")
    min_x, min_y, max_x, max_y = boundaries.total_bounds
    if not (126.0 < min_x < 128.0 and 126.0 < max_x < 128.0 and 37.0 < min_y < 38.0 and 37.0 < max_y < 38.0):
        raise ValueError("자치구 경계 좌표가 서울 범위를 벗어났습니다.")
    return pd.DataFrame({
        "district_code": boundaries["district_code"],
        "district_name": boundaries["district_name"],
        "geometry": boundaries.geometry.map(
            lambda geometry: json.dumps(
                {
                    "type": geometry.geom_type,
                    "coordinates": _rounded_coordinates(mapping(geometry)["coordinates"]),
                },
                separators=(",", ":"),
            )
        ),
    }).sort_values("district_code").reset_index(drop=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index = pd.read_parquet(SOURCE_DIR / "area_recommendation_index.parquet")
    profile = pd.read_parquet(SOURCE_DIR / "area_profile.parquet")
    latest = (
        profile.sort_values("quarter")
        .groupby("area_code", observed=True, sort=False)
        .tail(1)[["area_code", "admin_dong_name", "x_coord", "y_coord"]]
    )
    transformer = Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)
    longitude, latitude = transformer.transform(latest["x_coord"].to_numpy(), latest["y_coord"].to_numpy())
    latest = latest.assign(longitude=longitude, latitude=latitude).drop(columns=["x_coord", "y_coord"])
    index = index.merge(latest, on="area_code", how="left", validate="one_to_one")
    if index[["latitude", "longitude"]].isna().any().any():
        raise ValueError("일부 상권의 WGS84 좌표를 생성하지 못했습니다.")

    index_path = OUTPUT_DIR / "area_recommendation_index.parquet"
    evidence_path = OUTPUT_DIR / "area_industry_evidence.parquet"
    boundaries_path = OUTPUT_DIR / "area_boundaries.parquet"
    district_boundaries_path = OUTPUT_DIR / "district_boundaries.parquet"
    index.to_parquet(index_path, index=False)
    boundaries = build_area_boundaries(index)
    boundaries.to_parquet(boundaries_path, index=False)
    district_boundaries = build_district_boundaries(index)
    district_boundaries.to_parquet(district_boundaries_path, index=False)
    shutil.copy2(SOURCE_DIR / "area_industry_evidence.parquet", evidence_path)
    manifest = {
        "artifact_version": "2025q4-v3",
        "schema_version": 4,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "coordinate_reference": {"source": "EPSG:5181", "target": "EPSG:4326"},
        "area_boundary_source": {
            "name": "서울시 상권분석서비스(영역-상권)",
            "dataset_id": "OA-15560",
        },
        "district_boundary_source": {
            "name": "국가데이터처 행정구역 시군구 정보(JUSO)",
            "source_snapshot": "2015",
            "conversion": "southkorea/seoul-maps",
            "topology_repair": "shapely.make_valid",
        },
        "data_period": {"performance": "2021Q1~2025Q4", "profile": "2024Q1~2025Q4"},
        "files": {
            index_path.name: {"rows": len(index), "sha256": sha256(index_path)},
            evidence_path.name: {"rows": len(pd.read_parquet(evidence_path)), "sha256": sha256(evidence_path)},
            boundaries_path.name: {"rows": len(boundaries), "sha256": sha256(boundaries_path)},
            district_boundaries_path.name: {
                "rows": len(district_boundaries),
                "sha256": sha256(district_boundaries_path),
            },
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
