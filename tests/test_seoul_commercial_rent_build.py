from __future__ import annotations

import pandas as pd
import pytest

from scripts.refresh_seoul_commercial_rent import build_observations


def area_reference() -> pd.DataFrame:
    return pd.DataFrame([{
        "area_type_code": "A",
        "area_code": "3110001",
        "area_name": "테스트·상권",
        "admin_dong_code": "11110515",
        "admin_dong_name": "청운효자동",
        "district_code": "11110",
        "district_name": "종로구",
        "match_name": "테스트.상권",
    }])


def source_row(**overrides: str) -> dict[str, str]:
    row = {
        "NM": "테스트.상권 (청운효자동)",
        "GUBUN": "dong",
        "BF1_TOT_FLOOR": "99,000",
        "BF1_FST_FLOOR": "120000",
        "BF1_EX_FLOOR": "78000",
        "BF2_TOT_FLOOR": "102000",
        "BF2_FST_FLOOR": "123000",
        "BF2_EX_FLOOR": "81000",
        "BF3_TOT_FLOOR": "108900",
        "BF3_FST_FLOOR": "132000",
        "BF3_EX_FLOOR": " ",
    }
    row.update(overrides)
    return row


def test_builds_three_year_floor_observations_and_preserves_missing_bucket() -> None:
    source = {"A": [source_row()], "D": [], "R": [], "U": []}
    reference = area_reference()
    observations = build_observations(source, reference, year=2026, quarter=1)

    assert set(observations["reference_period"]) == {"2024Q1", "2025Q1", "2026Q1"}
    latest = observations.loc[observations["reference_period"].eq("2026Q1")]
    assert set(latest["floor"]) == {"all", "f1"}
    assert latest.loc[latest["floor"].eq("all"), "unit_converted_rent_krw_sqm"].iloc[0] == 33_000
    assert set(observations["annual_conversion_rate"]) == {0.12}
    assert observations.iloc[0]["area_name"] == "테스트·상권"


def test_rejects_unmatched_or_duplicate_source_area_names() -> None:
    reference = area_reference()
    with pytest.raises(ValueError, match="매칭 오류"):
        build_observations(
            {"A": [source_row(NM="다른 상권 (청운효자동)")], "D": [], "R": [], "U": []},
            reference,
            year=2026,
            quarter=1,
        )
    with pytest.raises(ValueError, match="중복"):
        build_observations(
            {"A": [source_row(), source_row()], "D": [], "R": [], "U": []},
            reference,
            year=2026,
            quarter=1,
        )


def test_uses_district_row_when_an_area_has_no_three_year_rent_values() -> None:
    blank = source_row(**{
        key: " " for prefix in ("BF1", "BF2", "BF3")
        for key in (f"{prefix}_TOT_FLOOR", f"{prefix}_FST_FLOOR", f"{prefix}_EX_FLOOR")
    })
    district = source_row(NM="종로구", GUBUN="gu")
    observations = build_observations(
        {"A": [blank, district], "D": [], "R": [], "U": []},
        area_reference(),
        year=2026,
        quarter=1,
    )
    assert set(observations["rent_basis_geography"]) == {"district"}
    assert set(observations["rent_basis_name"]) == {"종로구"}
