from __future__ import annotations

from app.schemas.agent import AgentPlanDraft
from app.services.agent.execution_plan_service import AgentExecutionPlanService
from app.services.agent.planner import AgentPlanningResult


PLAN = AgentPlanDraft.model_validate(
    {
        "requirement_summary": "订单创建后发送通知",
        "services": [
            {
                "name": "order-service",
                "reason": "发布订单事件",
                "change_scope": ["OrderCreated"],
            },
            {
                "name": "notification-service",
                "reason": "消费事件发送短信",
                "change_scope": ["短信消费者"],
            },
        ],
        "tasks": [
            {
                "id": "T1",
                "title": "发布订单事件",
                "service": "order-service",
                "description": "POST /orders 成功后发布 OrderCreated Event",
                "depends_on": [],
                "acceptance_criteria": ["OrderCreated 只发布一次"],
            },
            {
                "id": "T2",
                "title": "消费订单事件",
                "service": "notification-service",
                "description": "消费 OrderCreated Event 并写入 notification_delivery 表",
                "depends_on": ["T1"],
                "acceptance_criteria": ["消费后记录通知状态"],
            },
        ],
        "assumptions": [],
        "risks": [],
    }
)


class FakePlanner:
    def plan(self, *, requirement: str, system_context: str):
        assert requirement == "订单创建后发送短信"
        assert system_context == "system docs"
        return AgentPlanningResult(
            plan=PLAN,
            model="fake-model",
            prompt_token_count=100,
            completion_token_count=40,
        )


def test_execution_plan_service_composes_planner_dag_and_safety() -> None:
    service = AgentExecutionPlanService(planner=FakePlanner())

    result = service.create_plan(
        requirement="订单创建后发送短信",
        system_context="system docs",
    )

    assert result.model == "fake-model"
    assert result.prompt_token_count == 100
    assert result.completion_token_count == 40
    assert result.dependency.topological_order == ["T1", "T2"]
    assert result.dependency.critical_path == ["T1", "T2"]
    assert result.parallel_safety.total_tasks == 2
    assert [batch.task_ids for batch in result.parallel_safety.batches] == [
        ["T1"],
        ["T2"],
    ]
    assert result.planning_ms >= 0
