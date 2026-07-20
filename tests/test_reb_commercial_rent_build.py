from __future__ import annotations

import pandas as pd

from scripts.refresh_reb_commercial_rent import build_crosswalk, build_observations


def row(*, table: str, group: str | None, cls: str, item: str, value: float) -> dict:
    return {
        "STATBL_ID": table,
        "WRTTIME_IDTFR_ID": "202601",
        "GRP_NM": group if group else float("nan"),
        "GRP_FULLNM": f"서울>{group}" if group else float("nan"),
        "CLS_NM": cls,
        "CLS_FULLNM": f"서울>{cls}" if not group else cls,
        "ITM_NM": item,
        "DTA_VAL": value,
    }


def test_builds_normalized_observations_and_complete_nearest_crosswalk() -> None:
    downloaded = {
        "medium_large_retail": {
            "floor_rent": [
                row(table="floor", group="테스트상권", cls="1층", item="임대료", value=50),
            ],
            "regional_rent": [
                row(table="regional", group=None, cls="테스트상권", item="임대료", value=48),
            ],
            "conversion_rate": [
                row(table="rate", group=None, cls="테스트상권", item="전환율", value=6),
            ],
        }
    }
    observations = build_observations(downloaded, {"1층": "f1"})
    assert len(observations) == 1
    assert observations.iloc[0]["unit_converted_rent_krw_sqm"] == 50_000
    assert observations.iloc[0]["annual_conversion_rate"] == 0.06

    areas = pd.DataFrame([
        {"area_code": "A", "latitude": 37.5, "longitude": 127.0},
        {"area_code": "B", "latitude": 37.51, "longitude": 127.01},
    ])
    crosswalk = build_crosswalk(
        areas,
        observations,
        {"medium_large_retail": [{"secNm": "테스트 상권", "x": 127.0, "y": 37.5}]},
    )
    assert len(crosswalk) == 2
    assert set(crosswalk["survey_area_name"]) == {"테스트상권"}
    assert crosswalk.loc[crosswalk["area_code"].eq("A"), "distance_km"].iloc[0] == 0
