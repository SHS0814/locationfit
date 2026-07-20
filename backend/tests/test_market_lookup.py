from pathlib import Path

import pytest

from backend.app.services.recommender_service import RecommenderService


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


@pytest.fixture(scope="module")
def service() -> RecommenderService:
    return RecommenderService(ARTIFACT_DIR)


def test_ranks_areas_and_industries_by_sales(service: RecommenderService) -> None:
    areas = service.lookup_market_rankings(group_by="area", metric="sales", top_n=5)
    industries = service.lookup_market_rankings(group_by="industry", metric="sales", top_n=5)

    assert len(areas["rows"]) == 5
    assert len(industries["rows"]) == 5
    assert [row["metric_value"] for row in areas["rows"]] == sorted(
        (row["metric_value"] for row in areas["rows"]), reverse=True,
    )
    assert areas["rows"][0]["district_name"]
    assert industries["rows"][0]["entity_code"].startswith("CS")
    assert industries["metric_unit"] == "krw"
    assert industries["data_period"] == "2025Q1~2025Q4"
    assert industries["distribution"]["population_count"] == 62
    assert industries["distribution"]["standard_deviation"] > 0
    first = industries["rows"][0]
    assert first["difference_from_mean"] == pytest.approx(
        first["metric_value"] - industries["distribution"]["mean"], abs=0.01,
    )
    assert first["difference_from_median"] == pytest.approx(
        first["metric_value"] - industries["distribution"]["median"], abs=0.01,
    )
    assert first["standard_deviation_distance"] > 0


def test_ranks_closing_rate_by_industry_with_admin_dong_filter(
    service: RecommenderService,
) -> None:
    result = service.lookup_market_rankings(
        group_by="industry",
        metric="closing_rate",
        top_n=7,
        district_name="강남구",
        admin_dong_name="역삼1동",
    )

    assert len(result["rows"]) == 7
    assert result["filters"]["admin_dong_name"] == "역삼1동"
    assert [row["metric_value"] for row in result["rows"]] == sorted(
        (row["metric_value"] for row in result["rows"]), reverse=True,
    )
    assert result["rows"][0]["metric_display_value"].endswith("%")
    assert result["rows"][0]["difference_from_mean_display"].endswith("%p")
    assert result["distribution"]["standard_deviation_display"].endswith("%p")
    assert "행정동" in result["disclosure"]
    assert "법정동" in result["disclosure"]


def test_requires_district_for_ambiguous_admin_dong(service: RecommenderService) -> None:
    with pytest.raises(ValueError, match="여러 자치구"):
        service.lookup_market_rankings(
            group_by="industry",
            metric="closing_rate",
            admin_dong_name="신사동",
        )


def test_rejects_industry_breakdown_for_profile_metric(service: RecommenderService) -> None:
    with pytest.raises(ValueError, match="상권 단위"):
        service.lookup_market_rankings(group_by="industry", metric="floating_population")
