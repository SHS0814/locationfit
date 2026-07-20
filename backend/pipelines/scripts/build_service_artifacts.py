from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import mapping


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = PROJECT_ROOT / "data/processed"
OUTPUT_DIR = PROJECT_ROOT / "backend/artifacts/current"
BOUNDARY_SOURCE_DIR = PROJECT_ROOT / "data/raw/area"


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
    index.to_parquet(index_path, index=False)
    boundaries = build_area_boundaries(index)
    boundaries.to_parquet(boundaries_path, index=False)
    shutil.copy2(SOURCE_DIR / "area_industry_evidence.parquet", evidence_path)
    manifest = {
        "artifact_version": "2025q4-v1",
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "coordinate_reference": {"source": "EPSG:5181", "target": "EPSG:4326"},
        "area_boundary_source": {
            "name": "서울시 상권분석서비스(영역-상권)",
            "dataset_id": "OA-15560",
        },
        "data_period": {"performance": "2021Q1~2025Q4", "profile": "2024Q1~2025Q4"},
        "files": {
            index_path.name: {"rows": len(index), "sha256": sha256(index_path)},
            evidence_path.name: {"rows": len(pd.read_parquet(evidence_path)), "sha256": sha256(evidence_path)},
            boundaries_path.name: {"rows": len(boundaries), "sha256": sha256(boundaries_path)},
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
