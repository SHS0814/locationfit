from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.compare_reb_boundaries import compare


def test_compare_uses_latest_boundary_and_classifies_mapping() -> None:
    index = pd.DataFrame([
        {"area_code": "A", "area_name": "안쪽", "longitude": 127.0, "latitude": 37.5},
        {"area_code": "B", "area_name": "다른경계", "longitude": 127.2, "latitude": 37.5},
        {"area_code": "C", "area_name": "바깥", "longitude": 128.0, "latitude": 38.0},
    ])
    area_boundaries = pd.DataFrame([
        {"area_code": "A", "geometry": json.dumps(_polygon(126.95, 37.45, 127.05, 37.55))},
        {"area_code": "B", "geometry": json.dumps(_polygon(127.15, 37.45, 127.25, 37.55))},
        {"area_code": "C", "geometry": json.dumps(_polygon(127.95, 37.95, 128.05, 38.05))},
    ])
    crosswalk = pd.DataFrame([
        {"area_code": "A", "property_type": "small", "survey_area_name": "상권1"},
        {"area_code": "B", "property_type": "small", "survey_area_name": "상권1"},
        {"area_code": "C", "property_type": "small", "survey_area_name": "상권1"},
    ])
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": [
            _feature("2019", "이전경계", 126.9, 37.4, 127.3, 37.6),
            _feature("2024", "상권1", 126.9, 37.4, 127.1, 37.6),
            _feature("2024", "상권2", 127.1, 37.4, 127.3, 37.6),
        ],
    }

    result, summary, latest = compare(index, area_boundaries, crosswalk, payload)

    assert result.set_index("area_code")["mapping_status"].to_dict() == {
        "A": "inside_mapped_boundary",
        "B": "inside_different_boundary",
        "C": "outside_all_boundaries",
    }
    assert summary["boundary_latest_year"] == "2024"
    assert summary["boundary_features_latest_year"] == 2
    assert summary["inside_any_boundary_unique_areas"] == 2
    assert summary["outside_all_boundaries_unique_areas"] == 1
    assert summary["area_overlaps_any_boundary_unique_areas"] == 2
    assert summary["area_outside_all_boundaries_unique_areas"] == 1
    assert summary["by_property_type"]["small"]["inside_mapped_boundary"] == 1
    assert summary["by_property_type"]["small"]["area_overlaps_mapped_boundary"] == 1
    assert len(latest["features"]) == 2


def test_reb_property_type_gis_codes_match_official_map() -> None:
    config_path = Path(__file__).parents[1] / "config/reb_commercial_rent.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    types = config["property_types"]

    assert types["medium_large_retail"]["gis_building_code"] == "2"
    assert types["small_retail"]["gis_building_code"] == "4"
    assert types["strata_retail"]["gis_building_code"] == "3"


def _feature(year: str, name: str, min_x: float, min_y: float, max_x: float, max_y: float) -> dict:
    return {
        "type": "Feature",
        "properties": {"year": year, "cname": name},
        "geometry": _polygon(min_x, min_y, max_x, max_y),
    }


def _polygon(min_x: float, min_y: float, max_x: float, max_y: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y],
            [min_x, min_y],
        ]],
    }
