from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_recommender
from backend.app.schemas.recommendation import MetadataResponse
from backend.app.services.recommender_service import RecommenderService


router = APIRouter(tags=["metadata"])


@router.get("/metadata", response_model=MetadataResponse)
def metadata(service: RecommenderService = Depends(get_recommender)) -> MetadataResponse:
    return MetadataResponse(**service.metadata())
