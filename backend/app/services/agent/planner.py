from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol, Sequence

from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.agent import AgentPlanDraft
from app.services.llm.chat_service import (
    ChatGenerationError,
    ChatGenerationResult,
    LLMMessage,
    OllamaChatService,
)


class AgentPlanningError(RuntimeError):
    """Agent 无法生成可信的结构化研发计划。"""


class AgentChatModel(Protocol):
    def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.15,
    ) -> ChatGenerationResult:
        ...


@dataclass(frozen=True)
class AgentPlanningResult:
    plan: AgentPlanDraft
    model: str
    prompt_token_count: int | None
    completion_token_count: int | None


class AgentPlanner:
    """
    根据用户需求 + 系统技术文档生成结构化研发任务拆解。

    本组件负责：
    1. 找出需要改动的微服务；
    2. 拆成原子任务；
    3. 输出直接依赖关系；
    4. 使用 Pydantic 做结构和引用完整性校验。

    DAG 分层与资源冲突校验由后续确定性组件完成，避免把全部正确性寄托给 LLM。
    """

    SYSTEM_PROMPT = """你是企业研发团队的 AI Agent Planner。
你的职责不是编写代码，而是根据“用户需求”和“系统技术/接口文档”生成可执行的研发任务拆解。

必须遵守：
1. 只把确实需要修改的微服务放进 services；仅调用现有接口但不改代码的服务，不应列为受影响服务。
2. 微服务名称优先严格使用技术文档中的现有名称，不要凭空创造服务。
3. 每个 task 必须是单一、可验收的原子研发任务。
4. depends_on 只填写该任务真正需要等待完成的直接前置任务 ID。
5. task.id 必须从 T1 开始，使用 T1、T2、T3...。
6. task.service 必须是“单个字符串”，绝不能是数组、对象或空字符串。
7. 如果一个任务同时涉及两个微服务，必须拆成两个原子 task，并使用 depends_on 表达先后关系；绝不能写成 service: ["a", "b"]。
8. 任务引用的 service 必须存在于 services。
9. assumptions 必须是字符串数组；不要输出对象。
10. risks 必须是字符串数组；每条风险可在同一字符串中写“风险 + 缓解措施”，不要输出对象。
11. 如果文档不足以确认某个事实，把它写进 assumptions，不要伪造接口或规则。
12. 把跨服务接口兼容、事件一致性、幂等、失败补偿等风险写进 risks。
13. 只输出一个 JSON 对象，不要解释，不要 Markdown。

JSON 结构必须严格为：
{
  "requirement_summary": "一句话概括需求",
  "services": [
    {
      "name": "order-service",
      "reason": "为什么需要修改",
      "change_scope": ["需要改动的模块/接口/事件"]
    }
  ],
  "tasks": [
    {
      "id": "T1",
      "title": "任务标题",
      "service": "order-service",
      "description": "具体改动",
      "depends_on": [],
      "acceptance_criteria": ["可验证的验收条件"]
    }
  ],
  "assumptions": ["假设必须是一段字符串"],
  "risks": ["风险描述；缓解措施：具体做法"]
}
"""

    def __init__(
        self,
        *,
        chat_model: AgentChatModel | None = None,
        requirement_max_chars: int | None = None,
        system_context_max_chars: int | None = None,
        max_services: int | None = None,
        max_tasks: int | None = None,
        temperature: float | None = None,
        repair_attempts: int | None = None,
    ) -> None:
        settings = get_settings()
        self.chat_model = chat_model or OllamaChatService()
        self.requirement_max_chars = (
            requirement_max_chars
            if requirement_max_chars is not None
            else settings.agent_requirement_max_chars
        )
        self.system_context_max_chars = (
            system_context_max_chars
            if system_context_max_chars is not None
            else settings.agent_system_context_max_chars
        )
        self.max_services = (
            max_services
            if max_services is not None
            else settings.agent_max_services
        )
        self.max_tasks = (
            max_tasks
            if max_tasks is not None
            else settings.agent_max_tasks
        )
        self.temperature = (
            temperature
            if temperature is not None
            else settings.agent_planner_temperature
        )
        self.repair_attempts = (
            repair_attempts
            if repair_attempts is not None
            else settings.agent_planner_repair_attempts
        )

        if self.requirement_max_chars <= 0:
            raise ValueError("requirement_max_chars 必须大于 0")
        if self.system_context_max_chars <= 0:
            raise ValueError("system_context_max_chars 必须大于 0")
        if self.max_services <= 0 or self.max_tasks <= 0:
            raise ValueError("Agent 服务数和任务数上限必须大于 0")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("Agent Planner temperature 必须在 0 到 1 之间")
        if not 0 <= self.repair_attempts <= 2:
            raise ValueError("Agent Planner repair_attempts 必须在 0 到 2 之间")

    def plan(
        self,
        *,
        requirement: str,
        system_context: str,
    ) -> AgentPlanningResult:
        normalized_requirement = self._normalize_input(
            requirement,
            field_name="用户需求",
            max_chars=self.requirement_max_chars,
        )
        normalized_context = self._normalize_input(
            system_context,
            field_name="系统技术文档",
            max_chars=self.system_context_max_chars,
        )

        messages = [
            LLMMessage(role="system", content=self.SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    "【用户需求】\n"
                    f"{normalized_requirement}\n\n"
                    "【系统技术/接口文档】\n"
                    f"{normalized_context}\n\n"
                    "请严格按系统消息规定的 JSON 结构输出任务拆解。"
                ),
            ),
        ]

        try:
            generated = self.chat_model.generate(
                messages,
                temperature=self.temperature,
            )
        except ChatGenerationError as exc:
            raise AgentPlanningError(
                f"Agent Planner 调用 LLM 失败：{exc}"
            ) from exc

        try:
            plan = self._parse_plan(generated.content)
        except AgentPlanningError as exc:
            plan = self._repair_plan(
                requirement=normalized_requirement,
                system_context=normalized_context,
                invalid_content=generated.content,
                initial_error=exc,
            )
        self._enforce_business_limits(plan)

        return AgentPlanningResult(
            plan=plan,
            model=generated.model,
            prompt_token_count=generated.prompt_token_count,
            completion_token_count=generated.completion_token_count,
        )


    def _repair_plan(
        self,
        *,
        requirement: str,
        system_context: str,
        invalid_content: str,
        initial_error: AgentPlanningError,
    ) -> AgentPlanDraft:
        """对 LLM 的结构化输出做有限次数、只针对 Schema 的修复。

        真实本地模型偶尔会生成 `service: ""`、漏字段或引用不存在的
        task/service。这里不在 Python 端猜测业务归属，而是把明确的校验错误
        和原始技术文档回传给同一个 Planner，让模型只修 JSON 结构。
        """
        if self.repair_attempts == 0:
            raise initial_error

        last_error: AgentPlanningError = initial_error
        current_content = invalid_content

        schema_text = json.dumps(
            AgentPlanDraft.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )
        repair_system = (
            "你是 AI Agent Planner 的严格 JSON Schema 修复器。"
            "只能修复计划的 JSON/Schema/引用错误，不得改变用户需求，"
            "不得凭空新增技术文档中不存在的微服务、接口或业务规则。"
            "硬性规则："
            "tasks[*].service 必须是 services 中某一个微服务名称的单个字符串；"
            "绝不能是数组、对象或空字符串。"
            "如果一个 task 同时涉及多个微服务，必须拆成多个原子 task，"
            "重新编号并同步修正 depends_on。"
            "assumptions 必须是字符串数组。"
            "risks 必须是字符串数组；若上一版 risks 是对象数组，"
            "请把每个对象的风险描述和 mitigation 合并成一条完整字符串。"
            "只输出一个完整 JSON 对象，不要 Markdown，不要解释。"
        )

        for attempt_index in range(self.repair_attempts):
            repair_messages = [
                LLMMessage(role="system", content=repair_system),
                LLMMessage(
                    role="user",
                    content=(
                        f"【结构修复轮次】{attempt_index + 1}/{self.repair_attempts}\n\n"
                        "【用户需求】\n"
                        f"{requirement}\n\n"
                        "【系统技术/接口文档】\n"
                        f"{system_context}\n\n"
                        "【必须满足的 Pydantic JSON Schema】\n"
                        f"{schema_text}\n\n"
                        "【上一版输出】\n"
                        f"{current_content}\n\n"
                        "【校验错误】\n"
                        f"{last_error}\n\n"
                        "请重新检查每一个字段的 JSON 类型。"
                        "尤其检查 tasks[*].service、assumptions、risks。"
                        "保持业务含义正确，只修复结构问题并输出完整 JSON。"
                    ),
                ),
            ]

            try:
                repaired = self.chat_model.generate(
                    repair_messages,
                    temperature=0.0,
                )
            except ChatGenerationError as exc:
                raise AgentPlanningError(
                    f"Agent Planner 结构修复调用 LLM 失败：{exc}"
                ) from exc

            current_content = repaired.content
            try:
                return self._parse_plan(current_content)
            except AgentPlanningError as exc:
                last_error = exc

        raise AgentPlanningError(
            "Agent Planner 经过 "
            f"{self.repair_attempts} 次结构修复仍失败：{last_error}"
        ) from last_error

    def _parse_plan(self, content: str) -> AgentPlanDraft:
        candidate = self._extract_json_object(content)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise AgentPlanningError(
                "Agent Planner 未返回有效 JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise AgentPlanningError(
                "Agent Planner 顶层结果必须是 JSON object"
            )

        payload = self._canonicalize_payload(payload)
        self._reject_ambiguous_task_services(payload)

        try:
            return AgentPlanDraft.model_validate(payload)
        except ValidationError as exc:
            raise AgentPlanningError(
                "Agent Planner 返回结构不符合任务计划 Schema："
                f"{exc.errors(include_url=False)}"
            ) from exc

    @classmethod
    def _canonicalize_payload(
        cls,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """规范化不改变业务语义的常见 LLM JSON 类型漂移。

        仅处理可以无歧义转换的格式：
        - change_scope / depends_on / acceptance_criteria 的单字符串转列表；
        - 单元素 task.service 列表转字符串；
        - {"name": "..."} 形式的 task.service 转名称；
        - assumptions / risks 中的结构化对象完整压平为字符串。

        多服务 task.service 不做猜测，交给后续明确拒绝并触发 LLM 修复。
        """
        normalized = dict(payload)

        services = normalized.get("services")
        if isinstance(services, list):
            normalized_services: list[Any] = []
            for raw_service in services:
                if not isinstance(raw_service, dict):
                    normalized_services.append(raw_service)
                    continue
                service = dict(raw_service)
                change_scope = service.get("change_scope")
                if isinstance(change_scope, str):
                    value = change_scope.strip()
                    service["change_scope"] = [value] if value else []
                normalized_services.append(service)
            normalized["services"] = normalized_services

        tasks = normalized.get("tasks")
        if isinstance(tasks, list):
            normalized_tasks: list[Any] = []
            for raw_task in tasks:
                if not isinstance(raw_task, dict):
                    normalized_tasks.append(raw_task)
                    continue
                task = dict(raw_task)

                service_value = task.get("service")
                if (
                    isinstance(service_value, list)
                    and len(service_value) == 1
                    and isinstance(service_value[0], str)
                ):
                    task["service"] = service_value[0].strip()
                elif (
                    isinstance(service_value, dict)
                    and isinstance(service_value.get("name"), str)
                ):
                    task["service"] = service_value["name"].strip()

                for field_name in ("depends_on", "acceptance_criteria"):
                    field_value = task.get(field_name)
                    if isinstance(field_value, str):
                        value = field_value.strip()
                        task[field_name] = [value] if value else []

                normalized_tasks.append(task)
            normalized["tasks"] = normalized_tasks

        for field_name in ("assumptions", "risks"):
            values = normalized.get(field_name)
            if isinstance(values, list):
                normalized[field_name] = [
                    cls._stringify_narrative_item(item)
                    for item in values
                ]

        return normalized

    @staticmethod
    def _stringify_narrative_item(value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            parts: list[str] = []
            for key, item in value.items():
                if item is None:
                    continue
                if isinstance(item, (dict, list)):
                    rendered = json.dumps(
                        item,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                else:
                    rendered = str(item)
                parts.append(f"{key}: {rendered}")
            return "；".join(parts)
        return value

    @staticmethod
    def _reject_ambiguous_task_services(
        payload: dict[str, Any],
    ) -> None:
        tasks = payload.get("tasks")
        if not isinstance(tasks, list):
            return

        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            service_value = task.get("service")
            if isinstance(service_value, list):
                service_names = [
                    item.strip()
                    for item in service_value
                    if isinstance(item, str) and item.strip()
                ]
                if len(service_names) > 1:
                    raise AgentPlanningError(
                        "Agent Planner 返回了跨多个微服务的非原子任务："
                        f"tasks.{index}.service={service_names}。"
                        "必须把该任务拆成多个原子 task；每个 task.service "
                        "只能是一个字符串，并使用 depends_on 表达依赖关系。"
                    )

    def _enforce_business_limits(
        self,
        plan: AgentPlanDraft,
    ) -> None:
        if len(plan.services) > self.max_services:
            raise AgentPlanningError(
                "Agent Planner 返回的微服务数量超过限制："
                f"{len(plan.services)} > {self.max_services}"
            )
        if len(plan.tasks) > self.max_tasks:
            raise AgentPlanningError(
                "Agent Planner 返回的任务数量超过限制："
                f"{len(plan.tasks)} > {self.max_tasks}"
            )

    @staticmethod
    def _normalize_input(
        value: str,
        *,
        field_name: str,
        max_chars: int,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name}必须是字符串")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name}不能为空")
        if len(normalized) > max_chars:
            raise ValueError(
                f"{field_name}长度不能超过 {max_chars} 字符"
            )
        return normalized

    @staticmethod
    def _extract_json_object(content: str) -> str:
        if not isinstance(content, str) or not content.strip():
            raise AgentPlanningError("Agent Planner 返回了空内容")

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().lower() in {
                "```",
                "```json",
            }:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise AgentPlanningError(
                "Agent Planner 输出中没有 JSON object"
            )
        return text[start : end + 1]
