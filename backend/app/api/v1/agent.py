from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_location_agent, get_workspace_agent
from backend.app.schemas.agent import AgentTurnRequest, AgentTurnResponse, WorkspaceAgentRequest, WorkspaceAgentResponse
from backend.app.services.agent_service import LocationAgentService
from backend.app.services.workspace_agent_service import WorkspaceAgentService


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
        context=result["context"],
        assumptions=result["assumptions"],
        missing_fields=result["missing_fields"],
        confirmation_summary=result["confirmation_summary"],
        exploration_summary=result["exploration_summary"],
        scenarios=result["scenarios"],
        tradeoffs=result["tradeoffs"],
        relaxation_options=result["relaxation_options"],
        data_gaps=result["data_gaps"],
        selected_scenario_id=result["selected_scenario_id"],
        analysis_revision=result["analysis_revision"],
        recommendations=result["recommendations"],
        diagnostics=result["diagnostics"],
        comparison=result["comparison"],
        recommendation_report=result["recommendation_report"],
        market_lookup=result["market_lookup"],
    )


@router.post("/agent/workspace-turns", response_model=WorkspaceAgentResponse)
async def workspace_agent_turn(
    payload: WorkspaceAgentRequest,
    request: Request,
    service: WorkspaceAgentService = Depends(get_workspace_agent),
) -> WorkspaceAgentResponse:
    assistant_message = await service.turn(payload)
    return WorkspaceAgentResponse(
        request_id=request.state.request_id,
        workspace=payload.workspace,
        assistant_message=assistant_message,
    )
