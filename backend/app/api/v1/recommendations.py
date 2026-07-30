from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_recommender
from backend.app.schemas.recommendation import (
    RecommendationRequestSchema,
    RecommendationResponse,
)
from backend.app.services.recommender_service import RecommenderService

router = APIRouter(tags=["recommendations"])


@router.post("/recommendations", response_model=RecommendationResponse)
def recommend(
    payload: RecommendationRequestSchema,
    request: Request,
    service: RecommenderService = Depends(get_recommender),
) -> RecommendationResponse:
    recommendations, diagnostics = service.recommend(payload)
    return RecommendationResponse(
        request_id=request.state.request_id,
        artifact_version=service.artifact_version,
        recommendations=recommendations,
        diagnostics=diagnostics,
    )
