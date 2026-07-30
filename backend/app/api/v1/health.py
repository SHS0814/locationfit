from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(request: Request) -> dict[str, str]:
    service = getattr(request.app.state, "recommender", None)
    if service is None:
        raise RuntimeError(getattr(request.app.state, "startup_error", "추천 모델이 준비되지 않았습니다."))
    return {"status": "ready", "artifact_version": service.artifact_version}
