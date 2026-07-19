from fastapi import Request

from backend.app.services.recommender_service import RecommenderService


def get_recommender(request: Request) -> RecommenderService:
    service = getattr(request.app.state, "recommender", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "추천 모델이 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service
