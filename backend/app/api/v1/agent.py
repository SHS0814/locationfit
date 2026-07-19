from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_location_agent
from backend.app.schemas.agent import AgentTurnRequest, AgentTurnResponse
from backend.app.services.agent_service import LocationAgentService


router = APIRouter(tags=["agent"])


@router.post("/agent/turns", response_model=AgentTurnResponse)
async def agent_turn(
    payload: AgentTurnRequest,
    request: Request,
    service: LocationAgentService = Depends(get_location_agent),
) -> AgentTurnResponse:
    result = await service.turn(payload)
    return AgentTurnResponse(
        request_id=request.state.request_id,
        artifact_version=result["artifact_version"],
        assistant_message=result["assistant_message"],
        phase=result["phase"],
        draft=result["draft"],
        missing_fields=result["missing_fields"],
        confirmation_summary=result["confirmation_summary"],
        recommendations=result["recommendations"],
        diagnostics=result["diagnostics"],
        comparison=result["comparison"],
    )
