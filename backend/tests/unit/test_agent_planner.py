from __future__ import annotations

import json
from typing import Sequence

import pytest

from app.schemas.agent import AgentPlanDraft
from app.services.agent.planner import (
    AgentPlanner,
    AgentPlanningError,
)
from app.services.llm.chat_service import (
    ChatGenerationResult,
    LLMMessage,
)


VALID_PLAN = {
    "requirement_summary": "下单成功后自动发送短信通知",
    "services": [
        {
            "name": "order-service",
            "reason": "需要在订单成功后发布通知触发点",
            "change_scope": ["OrderCreated 事件"],
        },
        {
            "name": "notification-service",
            "reason": "需要消费订单事件并发送短信",
            "change_scope": ["订单通知消费者", "短信发送器"],
        },
    ],
    "tasks": [
        {
            "id": "T1",
            "title": "发布订单创建事件",
            "service": "order-service",
            "description": "订单创建成功后发布 OrderCreated 事件",
            "depends_on": [],
            "acceptance_criteria": ["订单成功后只发布一次事件"],
        },
        {
            "id": "T2",
            "title": "发送订单短信",
            "service": "notification-service",
            "description": "消费 OrderCreated 并调用短信通道",
            "depends_on": ["T1"],
            "acceptance_criteria": ["收到事件后发送短信"],
        },
    ],
    "assumptions": ["现有消息总线可用"],
    "risks": ["消息重复投递需要幂等"],
}


class FakeChatModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[list[LLMMessage], float]] = []

    def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.15,
    ) -> ChatGenerationResult:
        self.calls.append((list(messages), temperature))
        return ChatGenerationResult(
            content=self.content,
            model="fake-agent-model",
            prompt_token_count=120,
            completion_token_count=80,
            total_duration_ns=None,
            load_duration_ns=None,
        )


def make_planner(payload: object = VALID_PLAN, **kwargs: object) -> AgentPlanner:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return AgentPlanner(
        chat_model=FakeChatModel(content),
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=12,
        max_tasks=30,
        temperature=0.1,
        **kwargs,
    )


def test_planner_returns_structured_plan_and_usage() -> None:
    planner = make_planner()
    result = planner.plan(
        requirement="用户下单后自动发送短信通知",
        system_context="order-service 与 notification-service 技术文档",
    )

    assert isinstance(result.plan, AgentPlanDraft)
    assert [item.name for item in result.plan.services] == [
        "order-service",
        "notification-service",
    ]
    assert result.plan.tasks[1].depends_on == ["T1"]
    assert result.model == "fake-agent-model"
    assert result.prompt_token_count == 120
    assert result.completion_token_count == 80


def test_planner_prompt_contains_requirement_and_system_docs() -> None:
    fake = FakeChatModel(json.dumps(VALID_PLAN, ensure_ascii=False))
    planner = AgentPlanner(
        chat_model=fake,
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=12,
        max_tasks=30,
        temperature=0.1,
    )
    planner.plan(
        requirement="用户下单后发短信",
        system_context="order-service 发布 OrderCreated",
    )

    messages, temperature = fake.calls[0]
    assert messages[0].role == "system"
    assert "只把确实需要修改的微服务" in messages[0].content
    assert "用户下单后发短信" in messages[1].content
    assert "order-service 发布 OrderCreated" in messages[1].content
    assert temperature == 0.1


@pytest.mark.parametrize("value", ["", "  ", "\n\t"])
def test_empty_requirement_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="用户需求不能为空"):
        make_planner().plan(
            requirement=value,
            system_context="docs",
        )


def test_empty_system_context_is_rejected() -> None:
    with pytest.raises(ValueError, match="系统技术文档不能为空"):
        make_planner().plan(
            requirement="需求",
            system_context=" ",
        )


def test_requirement_length_limit_is_enforced() -> None:
    planner = AgentPlanner(
        chat_model=FakeChatModel(json.dumps(VALID_PLAN)),
        requirement_max_chars=4,
        system_context_max_chars=100,
        max_services=12,
        max_tasks=30,
        temperature=0.1,
    )
    with pytest.raises(ValueError, match="不能超过 4 字符"):
        planner.plan(
            requirement="12345",
            system_context="docs",
        )


def test_json_code_fence_is_accepted() -> None:
    payload = json.dumps(VALID_PLAN, ensure_ascii=False)
    planner = make_planner(f"```json\n{payload}\n```")
    result = planner.plan(
        requirement="需求",
        system_context="docs",
    )
    assert result.plan.tasks[0].id == "T1"


def test_invalid_json_is_rejected() -> None:
    planner = make_planner("this is not json")
    with pytest.raises(AgentPlanningError, match="没有 JSON object"):
        planner.plan(
            requirement="需求",
            system_context="docs",
        )


def test_duplicate_task_id_is_rejected() -> None:
    payload = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    payload["tasks"][1]["id"] = "T1"
    planner = make_planner(payload)
    with pytest.raises(AgentPlanningError, match="重复任务 ID"):
        planner.plan(
            requirement="需求",
            system_context="docs",
        )


def test_unknown_dependency_is_rejected() -> None:
    payload = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    payload["tasks"][1]["depends_on"] = ["T99"]
    planner = make_planner(payload)
    with pytest.raises(AgentPlanningError, match="不存在的依赖任务"):
        planner.plan(
            requirement="需求",
            system_context="docs",
        )


def test_task_service_must_exist_in_services() -> None:
    payload = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    payload["tasks"][1]["service"] = "ghost-service"
    planner = make_planner(payload)
    with pytest.raises(AgentPlanningError, match="不存在的微服务"):
        planner.plan(
            requirement="需求",
            system_context="docs",
        )


def test_service_limit_is_enforced_after_schema_validation() -> None:
    planner = AgentPlanner(
        chat_model=FakeChatModel(json.dumps(VALID_PLAN, ensure_ascii=False)),
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=1,
        max_tasks=30,
        temperature=0.1,
    )
    with pytest.raises(AgentPlanningError, match="微服务数量超过限制"):
        planner.plan(
            requirement="需求",
            system_context="docs",
        )


def test_task_limit_is_enforced_after_schema_validation() -> None:
    planner = AgentPlanner(
        chat_model=FakeChatModel(json.dumps(VALID_PLAN, ensure_ascii=False)),
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=12,
        max_tasks=1,
        temperature=0.1,
    )
    with pytest.raises(AgentPlanningError, match="任务数量超过限制"):
        planner.plan(
            requirement="需求",
            system_context="docs",
        )


class SequenceChatModel:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls: list[tuple[list[LLMMessage], float]] = []

    def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.15,
    ) -> ChatGenerationResult:
        self.calls.append((list(messages), temperature))
        if not self.contents:
            raise AssertionError("SequenceChatModel 没有更多响应")
        return ChatGenerationResult(
            content=self.contents.pop(0),
            model="fake-agent-model",
            prompt_token_count=120,
            completion_token_count=80,
            total_duration_ns=None,
            load_duration_ns=None,
        )


def test_schema_failure_is_repaired_once() -> None:
    invalid = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    invalid["tasks"][1]["service"] = ""
    fake = SequenceChatModel(
        [
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(VALID_PLAN, ensure_ascii=False),
        ]
    )
    planner = AgentPlanner(
        chat_model=fake,
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=12,
        max_tasks=30,
        temperature=0.1,
        repair_attempts=1,
    )

    result = planner.plan(
        requirement="用户下单后自动发送短信",
        system_context="order-service 与 notification-service 技术文档",
    )

    assert result.plan.tasks[1].service == "notification-service"
    assert len(fake.calls) == 2
    assert fake.calls[1][1] == 0.0


def test_repair_prompt_contains_validation_error_and_original_output() -> None:
    invalid = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    invalid["tasks"][1]["service"] = ""
    invalid_text = json.dumps(invalid, ensure_ascii=False)
    fake = SequenceChatModel(
        [invalid_text, json.dumps(VALID_PLAN, ensure_ascii=False)]
    )
    planner = AgentPlanner(
        chat_model=fake,
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=12,
        max_tasks=30,
        temperature=0.1,
        repair_attempts=1,
    )

    planner.plan(
        requirement="用户下单后自动发送短信",
        system_context="notification-service 负责短信发送",
    )

    repair_messages, _ = fake.calls[1]
    repair_text = repair_messages[1].content
    assert "【上一版输出】" in repair_text
    assert invalid_text in repair_text
    assert "【校验错误】" in repair_text
    assert "('tasks', 1, 'service')" in repair_text
    assert "notification-service 负责短信发送" in repair_text



def test_structured_risks_and_assumptions_are_canonicalized() -> None:
    payload = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    payload["assumptions"] = [
        {
            "id": "A1",
            "description": "短信通道已配置",
        }
    ]
    payload["risks"] = [
        {
            "id": "R1",
            "title": "短信失败",
            "description": "供应商可能超时",
            "mitigation": "记录失败原因并异步重试",
        }
    ]
    planner = make_planner(payload)

    result = planner.plan(
        requirement="用户下单后自动发送短信",
        system_context="docs",
    )

    assert isinstance(result.plan.assumptions[0], str)
    assert "短信通道已配置" in result.plan.assumptions[0]
    assert isinstance(result.plan.risks[0], str)
    assert "短信失败" in result.plan.risks[0]
    assert "记录失败原因并异步重试" in result.plan.risks[0]


def test_singleton_task_service_list_is_canonicalized() -> None:
    payload = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    payload["tasks"][1]["service"] = ["notification-service"]
    planner = make_planner(payload)

    result = planner.plan(
        requirement="用户下单后自动发送短信",
        system_context="docs",
    )

    assert result.plan.tasks[1].service == "notification-service"


def test_second_repair_attempt_can_fix_multi_service_task() -> None:
    first = json.loads(json.dumps(VALID_PLAN, ensure_ascii=False))
    first["tasks"][1]["service"] = [
        "order-service",
        "notification-service",
    ]
    first["risks"] = [
        {
            "id": "R1",
            "title": "跨服务一致性风险",
            "mitigation": "使用事件幂等键",
        }
    ]

    second = json.loads(json.dumps(first, ensure_ascii=False))
    # 第一次修复仍错误，验证 Planner 会继续做第二轮，而不是提前接受。
    second["tasks"][1]["service"] = [
        "order-service",
        "notification-service",
    ]

    fake = SequenceChatModel(
        [
            json.dumps(first, ensure_ascii=False),
            json.dumps(second, ensure_ascii=False),
            json.dumps(VALID_PLAN, ensure_ascii=False),
        ]
    )
    planner = AgentPlanner(
        chat_model=fake,
        requirement_max_chars=1000,
        system_context_max_chars=5000,
        max_services=12,
        max_tasks=30,
        temperature=0.1,
        repair_attempts=2,
    )

    result = planner.plan(
        requirement="用户下单后自动发送短信",
        system_context=(
            "order-service 负责订单；"
            "notification-service 负责短信通知。"
        ),
    )

    assert result.plan.tasks[1].service == "notification-service"
    assert len(fake.calls) == 3
    assert fake.calls[1][1] == 0.0
    assert fake.calls[2][1] == 0.0
    second_repair_text = fake.calls[2][0][1].content
    assert "Pydantic JSON Schema" in second_repair_text
    assert "tasks[*].service" in fake.calls[2][0][0].content
