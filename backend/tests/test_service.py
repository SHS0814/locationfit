from pathlib import Path

from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.services.recommender_service import RecommenderService


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


def test_metadata_and_recommendation_with_real_artifacts() -> None:
    service = RecommenderService(ARTIFACT_DIR)
    metadata = service.metadata()
    assert len(metadata["industries"]) == 63
    assert "강남구" in metadata["districts"]

    request = RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20", "30"],
        floating_population_importance=0.7,
        top_n=5,
    )
    recommendations, diagnostics = service.recommend(request)
    assert len(recommendations) == 5
    assert diagnostics["returned"] == 5
    assert all(37.0 < item["latitude"] < 38.0 for item in recommendations)
    assert all(126.0 < item["longitude"] < 128.0 for item in recommendations)
    assert isinstance(recommendations[0]["positive_reasons"], list)
