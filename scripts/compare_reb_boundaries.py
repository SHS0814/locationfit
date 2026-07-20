#!/usr/bin/env python3
"""Download official R-ONE commercial-market boundaries and compare point containment."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import tempfile

import pandas as pd
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

from src.data.reb_api import RebGisClient


ROOT = Path(__file__).resolve().parents[1]
WFS_URL = "https://www.reb.or.kr/r-one/portal/gis/getCommercialWFS.do"


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        temp = Path(stream.name)
    temp.chmod(0o644)
    temp.replace(path)


def atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as stream:
        temp = Path(stream.name)
    try:
        frame.to_parquet(temp, index=False)
        temp.chmod(0o644)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def compare(
    index: pd.DataFrame,
    area_boundaries: pd.DataFrame,
    crosswalk: pd.DataFrame,
    boundary_payload: dict,
) -> tuple[pd.DataFrame, dict[str, object], dict]:
    features = boundary_payload["features"]
    latest_year = max(str(feature["properties"].get("year", "")) for feature in features)
    latest = [feature for feature in features if str(feature["properties"].get("year")) == latest_year]
    boundaries = [
        (str(feature["properties"]["cname"]), make_valid(shape(feature["geometry"])))
        for feature in latest
    ]
    boundary_names = {name for name, _ in boundaries}
    project = Transformer.from_crs(4326, 5179, always_xy=True).transform
    projected_boundaries = [(name, make_valid(transform(project, polygon))) for name, polygon in boundaries]
    projected_boundary_by_name = dict(projected_boundaries)
    projected_boundary_union = make_valid(unary_union([polygon for _, polygon in projected_boundaries]))
    projected_area_by_code = {
        str(row.area_code): make_valid(transform(project, make_valid(shape(json.loads(row.geometry)))))
        for row in area_boundaries.itertuples(index=False)
    }

    containment: list[dict[str, object]] = []
    for area in index.itertuples(index=False):
        point = Point(float(area.longitude), float(area.latitude))
        names = sorted(name for name, polygon in boundaries if polygon.covers(point))
        area_polygon = projected_area_by_code[str(area.area_code)]
        overlap_names = sorted(
            name for name, polygon in projected_boundaries
            if area_polygon.intersection(polygon).area > 0
        )
        overlap_ratio = (
            area_polygon.intersection(projected_boundary_union).area / area_polygon.area
            if area_polygon.area else 0.0
        )
        containment.append({
            "area_code": str(area.area_code),
            "area_name": str(area.area_name),
            "inside_any_reb_boundary": bool(names),
            "containing_boundary_count": len(names),
            "containing_reb_boundary_names": "|".join(names),
            "overlaps_any_reb_boundary": bool(overlap_names),
            "overlapping_boundary_count": len(overlap_names),
            "overlapping_reb_boundary_names": "|".join(overlap_names),
            "reb_boundary_overlap_ratio": overlap_ratio,
        })
    contained = pd.DataFrame(containment)
    compared = crosswalk.copy()
    compared["area_code"] = compared["area_code"].astype(str)
    compared = compared.merge(contained, on="area_code", how="left", validate="many_to_one")
    compared["mapped_boundary_exists"] = compared["survey_area_name"].astype(str).isin(boundary_names)
    compared["inside_mapped_reb_boundary"] = compared.apply(
        lambda row: str(row["survey_area_name"]) in str(row["containing_reb_boundary_names"]).split("|")
        if row["inside_any_reb_boundary"] else False,
        axis=1,
    )
    compared["mapped_boundary_overlap_ratio"] = [
        (
            projected_area_by_code[str(row.area_code)].intersection(
                projected_boundary_by_name[str(row.survey_area_name)]
            ).area / projected_area_by_code[str(row.area_code)].area
            if str(row.survey_area_name) in projected_boundary_by_name
            and projected_area_by_code[str(row.area_code)].area
            else 0.0
        )
        for row in compared.itertuples(index=False)
    ]
    compared["overlaps_mapped_reb_boundary"] = compared["mapped_boundary_overlap_ratio"].gt(0)
    compared["mapping_status"] = "outside_all_boundaries"
    compared.loc[
        compared["inside_any_reb_boundary"] & ~compared["inside_mapped_reb_boundary"],
        "mapping_status",
    ] = "inside_different_boundary"
    compared.loc[compared["inside_mapped_reb_boundary"], "mapping_status"] = "inside_mapped_boundary"
    compared["polygon_mapping_status"] = "outside_all_boundaries"
    compared.loc[
        compared["overlaps_any_reb_boundary"] & ~compared["overlaps_mapped_reb_boundary"],
        "polygon_mapping_status",
    ] = "overlaps_different_boundary"
    compared.loc[
        compared["overlaps_mapped_reb_boundary"], "polygon_mapping_status"
    ] = "overlaps_mapped_boundary"

    by_type: dict[str, object] = {}
    for property_type, rows in compared.groupby("property_type", sort=True):
        by_type[str(property_type)] = {
            "mapped_areas": len(rows),
            "mapped_survey_markets": int(rows["survey_area_name"].nunique()),
            "mapped_names_with_2024_boundary": int(
                rows.loc[rows["mapped_boundary_exists"], "survey_area_name"].nunique()
            ),
            "inside_any_boundary": int(rows["inside_any_reb_boundary"].sum()),
            "inside_any_boundary_pct": round(float(rows["inside_any_reb_boundary"].mean() * 100), 2),
            "inside_mapped_boundary": int(rows["inside_mapped_reb_boundary"].sum()),
            "inside_mapped_boundary_pct": round(float(rows["inside_mapped_reb_boundary"].mean() * 100), 2),
            "inside_different_boundary": int(
                rows["mapping_status"].eq("inside_different_boundary").sum()
            ),
            "outside_all_boundaries": int(
                rows["mapping_status"].eq("outside_all_boundaries").sum()
            ),
            "outside_all_boundaries_pct": round(float(
                rows["mapping_status"].eq("outside_all_boundaries").mean() * 100
            ), 2),
            "area_overlaps_mapped_boundary": int(rows["overlaps_mapped_reb_boundary"].sum()),
            "area_overlaps_mapped_boundary_pct": round(float(
                rows["overlaps_mapped_reb_boundary"].mean() * 100
            ), 2),
            "area_at_least_50pct_inside_mapped_boundary": int(
                rows["mapped_boundary_overlap_ratio"].ge(0.5).sum()
            ),
            "area_at_least_99pct_inside_mapped_boundary": int(
                rows["mapped_boundary_overlap_ratio"].ge(0.99).sum()
            ),
        }
    unique_contained = contained.drop_duplicates("area_code")
    summary: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "boundary_source": WFS_URL,
        "boundary_crs": boundary_payload.get("crs"),
        "boundary_latest_year": latest_year,
        "boundary_features_all_years": len(features),
        "boundary_features_latest_year": len(latest),
        "existing_area_count": len(unique_contained),
        "inside_any_boundary_unique_areas": int(unique_contained["inside_any_reb_boundary"].sum()),
        "inside_any_boundary_unique_areas_pct": round(float(
            unique_contained["inside_any_reb_boundary"].mean() * 100
        ), 2),
        "outside_all_boundaries_unique_areas": int(
            (~unique_contained["inside_any_reb_boundary"]).sum()
        ),
        "overlapping_boundary_areas": int(
            unique_contained["containing_boundary_count"].gt(1).sum()
        ),
        "area_overlaps_any_boundary_unique_areas": int(
            unique_contained["overlaps_any_reb_boundary"].sum()
        ),
        "area_overlaps_any_boundary_unique_areas_pct": round(float(
            unique_contained["overlaps_any_reb_boundary"].mean() * 100
        ), 2),
        "area_outside_all_boundaries_unique_areas": int(
            (~unique_contained["overlaps_any_reb_boundary"]).sum()
        ),
        "area_at_least_50pct_inside_any_boundary": int(
            unique_contained["reb_boundary_overlap_ratio"].ge(0.5).sum()
        ),
        "area_at_least_99pct_inside_any_boundary": int(
            unique_contained["reb_boundary_overlap_ratio"].ge(0.99).sum()
        ),
        "centroid_outside_but_area_overlaps": int((
            ~unique_contained["inside_any_reb_boundary"]
            & unique_contained["overlaps_any_reb_boundary"]
        ).sum()),
        "by_property_type": by_type,
        "limitation": (
            "R-ONE 화면이 제공하는 최신 WFS 경계는 2024년판이며, 사이트는 2024Q3 이후 "
            "표본 재설계 경계 변경 작업 중이라고 안내한다. 2026Q1 임대료와 시점이 다르므로 진단용이다. "
            "면적 교차율은 두 경계를 EPSG:5179로 투영해 계산했다."
        ),
    }
    latest_geojson = {
        **{key: value for key, value in boundary_payload.items() if key != "features"},
        "features": latest,
        "totalFeatures": len(latest),
        "numberMatched": len(latest),
        "numberReturned": len(latest),
    }
    return compared.sort_values(["property_type", "area_code"]).reset_index(drop=True), summary, latest_geojson


def main() -> None:
    parser = argparse.ArgumentParser(description="REB 공식 상권 경계 다운로드 및 기존 상권 포함 비교")
    parser.add_argument(
        "--artifact-dir", type=Path, default=ROOT / "backend/artifacts/current",
    )
    parser.add_argument(
        "--raw-dir", type=Path, default=ROOT / "data/raw/reb_commercial_boundaries",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/tables",
    )
    parser.add_argument(
        "--from-raw",
        type=Path,
        help="이미 내려받은 전체 연도 GeoJSON을 사용하고 네트워크 조회를 건너뜁니다.",
    )
    args = parser.parse_args()

    payload = (
        json.loads(args.from_raw.read_text(encoding="utf-8"))
        if args.from_raw
        else RebGisClient(base_url=WFS_URL).fetch_seoul_boundaries()
    )
    compared, summary, latest_geojson = compare(
        pd.read_parquet(args.artifact_dir / "area_recommendation_index.parquet"),
        pd.read_parquet(args.artifact_dir / "area_boundaries.parquet"),
        pd.read_parquet(args.artifact_dir / "commercial_rent_crosswalk.parquet"),
        payload,
    )
    if not args.from_raw:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_target = args.raw_dir / stamp
        atomic_json(raw_target / "seoul_boundaries_all_years.geojson", payload)
        atomic_json(raw_target / "seoul_boundaries_latest.geojson", latest_geojson)
        atomic_json(raw_target / "download_meta.json", {
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "source": WFS_URL,
            "api_key_required": False,
            "latest_year": summary["boundary_latest_year"],
        })
    atomic_parquet(args.output_dir / "reb_boundary_mapping_comparison.parquet", compared)
    atomic_json(args.output_dir / "reb_boundary_mapping_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
