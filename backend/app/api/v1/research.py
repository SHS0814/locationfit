from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_web_research_service
from backend.app.core.ai_security import require_ai_request
from backend.app.schemas.research import WebResearchRequest, WebResearchResponse
from backend.app.services.web_research_service import WebResearchService

router = APIRouter(tags=["agent-research"])


@router.post("/agent/web-research", response_model=WebResearchResponse)
async def web_research(
    payload: WebResearchRequest,
    request: Request,
    _permit: object = Depends(require_ai_request),
    service: WebResearchService = Depends(get_web_research_service),
) -> WebResearchResponse:
    result = await service.research(payload)
    return WebResearchResponse(request_id=request.state.request_id, **result)

