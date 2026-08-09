from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    get_agent_execution_plan_service,
    get_current_admin,
    get_current_user,
)
from app.main import app
from app.schemas.agent import (
    AgentDependencyAnalysis,
    AgentExecutionStage,
    AgentParallelSafetyAnalysis,
    AgentPlanDraft,
    AgentSafeExecutionBatch,
    AgentTaskResourceProfile,
)
from app.services.agent.execution_plan_service import AgentExecutionPlanResult


PLAN = AgentPlanDraft.model_validate(
    {
        "requirement_summary": "订单创建后发送短信",
        "services": [
            {
                "name": "order-service",
                "reason": "发布事件",
                "change_scope": ["OrderCreated"],
            }
        ],
        "tasks": [
            {
                "id": "T1",
                "title": "发布订单事件",
                "service": "order-service",
                "description": "发布 OrderCreated",
                "depends_on": [],
                "acceptance_criteria": ["事件发布成功"],
            }
        ],
        "assumptions": [],
        "risks": [],
    }
)


class FakeExecutionPlanService:
    def create_plan(self, *, requirement: str, system_context: str):
        assert requirement == "订单创建后发送短信"
        assert system_context == "order-service 技术文档"
        return AgentExecutionPlanResult(
            plan=PLAN,
            dependency=AgentDependencyAnalysis(
                total_tasks=1,
                edges=[],
                topological_order=["T1"],
                stages=[
                    AgentExecutionStage(
                        index=1,
                        task_ids=["T1"],
                        parallel_candidate=False,
                    )
                ],
                root_tasks=["T1"],
                terminal_tasks=["T1"],
                critical_path=["T1"],
                max_parallelism=1,
            ),
            parallel_safety=AgentParallelSafetyAnalysis(
                total_tasks=1,
                candidate_parallel_stages=0,
                task_resources=[
                    AgentTaskResourceProfile(
                        task_id="T1",
                        service="order-service",
                        resources=["event:ordercreated"],
                    )
                ],
                conflicts=[],
                batches=[
                    AgentSafeExecutionBatch(
                        stage_index=1,
                        batch_index=1,
                        task_ids=["T1"],
                        parallel_safe=False,
                    )
                ],
                max_safe_parallelism=1,
            ),
            model="qwen3.5:4b",
            prompt_token_count=123,
            completion_token_count=56,
            planning_ms=321,
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def admin_client():
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        status="active",
    )
    app.dependency_overrides[get_agent_execution_plan_service] = (
        lambda: FakeExecutionPlanService()
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_agent_openapi_path_is_registered(admin_client):
    paths = (await admin_client.get("/openapi.json")).json()["paths"]
    assert "/api/v1/agent/plans" in paths


@pytest.mark.anyio
async def test_admin_can_generate_agent_plan(admin_client):
    response = await admin_client.post(
        "/api/v1/agent/plans",
        json={
            "requirement": "订单创建后发送短信",
            "system_context": "order-service 技术文档",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "qwen3.5:4b"
    assert body["plan"]["tasks"][0]["id"] == "T1"
    assert body["dependency"]["critical_path"] == ["T1"]
    assert body["parallel_safety"]["batches"][0]["task_ids"] == ["T1"]


@pytest.mark.anyio
async def test_agent_api_rejects_blank_requirement(admin_client):
    response = await admin_client.post(
        "/api/v1/agent/plans",
        json={
            "requirement": "   ",
            "system_context": "docs",
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_non_admin_cannot_generate_agent_plan():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        role="user",
        status="active",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/agent/plans",
            json={
                "requirement": "订单创建后发送短信",
                "system_context": "docs",
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 403
