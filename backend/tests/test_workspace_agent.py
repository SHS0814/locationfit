import asyncio

from backend.app.schemas.agent import WorkspaceAgentRequest
from backend.app.services.workspace_agent_service import WorkspaceAgentService


class RecordingRunner:
    def __init__(self) -> None:
        self.workspace = None
        self.conversation = None

    async def run(self, workspace, conversation):
        self.workspace = workspace
        self.conversation = conversation
        return "현재 상권의 점포 집계만 기준으로 설명했습니다."


def test_workspace_agent_keeps_page_scope_and_context() -> None:
    runner = RecordingRunner()
    service = WorkspaceAgentService(runner, timeout_seconds=1)
    result = asyncio.run(service.turn(WorkspaceAgentRequest(
        workspace="stores",
        message="경쟁점이 많아?",
        history=[{"role": "assistant", "content": "점포분석만 답합니다."}],
        context={"summary": {"competitor_count": 12}},
    )))

    assert result == "현재 상권의 점포 집계만 기준으로 설명했습니다."
    assert runner.workspace == "stores"
    assert runner.conversation["context"]["summary"]["competitor_count"] == 12
    assert runner.conversation["history"] == [
        {"role": "assistant", "content": "점포분석만 답합니다."},
    ]


def test_workspace_agent_request_rejects_unknown_workspace() -> None:
    try:
        WorkspaceAgentRequest(workspace="recommendation", message="질문")
    except ValueError as exc:
        assert "workspace" in str(exc)
    else:
        raise AssertionError("unknown workspace must be rejected")
