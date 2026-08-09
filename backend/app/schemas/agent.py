from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentServiceImpact(BaseModel):
    """Agent 判断出的受影响微服务。"""

    name: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)
    change_scope: list[str] = Field(min_length=1, max_length=8)

    @field_validator("name", "reason", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("change_scope", mode="before")
    @classmethod
    def normalize_scope(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                result.append(item)
                continue
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            result.append(normalized)
            seen.add(normalized)
        return result


class AgentTaskDraft(BaseModel):
    """由 Planner 生成的原子研发任务。"""

    id: str = Field(pattern=r"^T[1-9][0-9]*$")
    title: str = Field(min_length=1, max_length=160)
    service: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1500)
    depends_on: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=8)

    @field_validator("id", "title", "service", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("depends_on", "acceptance_criteria", mode="before")
    @classmethod
    def normalize_string_list(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                result.append(item)
                continue
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            result.append(normalized)
            seen.add(normalized)
        return result


class AgentPlanDraft(BaseModel):
    """LLM Planner 的结构化任务拆解结果。"""

    requirement_summary: str = Field(min_length=1, max_length=1200)
    services: list[AgentServiceImpact] = Field(min_length=1, max_length=30)
    tasks: list[AgentTaskDraft] = Field(min_length=1, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    risks: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("requirement_summary", mode="before")
    @classmethod
    def strip_summary(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("assumptions", "risks", mode="before")
    @classmethod
    def normalize_notes(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                result.append(item)
                continue
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            result.append(normalized)
            seen.add(normalized)
        return result

    @model_validator(mode="after")
    def validate_references(self) -> "AgentPlanDraft":
        service_names = [item.name for item in self.services]
        if len(service_names) != len(set(service_names)):
            raise ValueError("services 中存在重复微服务")

        task_ids = [item.id for item in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("tasks 中存在重复任务 ID")

        service_set = set(service_names)
        task_set = set(task_ids)
        for task in self.tasks:
            if task.service not in service_set:
                raise ValueError(
                    f"任务 {task.id} 引用了 services 中不存在的微服务：{task.service}"
                )
            for dependency in task.depends_on:
                if dependency == task.id:
                    raise ValueError(f"任务 {task.id} 不能依赖自身")
                if dependency not in task_set:
                    raise ValueError(
                        f"任务 {task.id} 引用了不存在的依赖任务：{dependency}"
                    )
        return self



class AgentDependencyEdge(BaseModel):
    """任务依赖边：source 必须先于 target 完成。"""

    source: str = Field(pattern=r"^T[1-9][0-9]*$")
    target: str = Field(pattern=r"^T[1-9][0-9]*$")


class AgentExecutionStage(BaseModel):
    """DAG 拓扑分层中的一个执行阶段。"""

    index: int = Field(ge=1)
    task_ids: list[str] = Field(min_length=1)
    parallel_candidate: bool = False


class AgentDependencyAnalysis(BaseModel):
    """Agent 任务依赖图分析结果。"""

    total_tasks: int = Field(ge=1)
    edges: list[AgentDependencyEdge] = Field(default_factory=list)
    topological_order: list[str] = Field(min_length=1)
    stages: list[AgentExecutionStage] = Field(min_length=1)
    root_tasks: list[str] = Field(default_factory=list)
    terminal_tasks: list[str] = Field(default_factory=list)
    critical_path: list[str] = Field(min_length=1)
    max_parallelism: int = Field(ge=1)

class AgentTaskResourceProfile(BaseModel):
    """从原子任务中提取出的可冲突资源集合。"""

    task_id: str = Field(pattern=r"^T[1-9][0-9]*$")
    service: str = Field(min_length=1, max_length=80)
    resources: list[str] = Field(default_factory=list)


class AgentResourceConflict(BaseModel):
    """同一 DAG Stage 中两个任务的资源冲突。"""

    stage_index: int = Field(ge=1)
    task_a: str = Field(pattern=r"^T[1-9][0-9]*$")
    task_b: str = Field(pattern=r"^T[1-9][0-9]*$")
    shared_resources: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=1000)


class AgentSafeExecutionBatch(BaseModel):
    """同一拓扑 Stage 内可安全同时执行的一批任务。"""

    stage_index: int = Field(ge=1)
    batch_index: int = Field(ge=1)
    task_ids: list[str] = Field(min_length=1)
    parallel_safe: bool = False


class AgentParallelSafetyAnalysis(BaseModel):
    """DAG 候选并行任务经过资源冲突检查后的最终分析。"""

    total_tasks: int = Field(ge=1)
    candidate_parallel_stages: int = Field(ge=0)
    task_resources: list[AgentTaskResourceProfile] = Field(default_factory=list)
    conflicts: list[AgentResourceConflict] = Field(default_factory=list)
    batches: list[AgentSafeExecutionBatch] = Field(min_length=1)
    max_safe_parallelism: int = Field(ge=1)



class AgentPlanRequest(BaseModel):
    """通过 HTTP API 请求 Agent 生成研发执行计划。"""

    requirement: str = Field(min_length=1, max_length=4000)
    system_context: str = Field(min_length=1, max_length=24000)

    @field_validator("requirement", "system_context", mode="before")
    @classmethod
    def normalize_agent_request_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class AgentPlanResponse(BaseModel):
    """Agent Planner + DAG + 资源安全分析的完整 API 响应。"""

    plan: AgentPlanDraft
    dependency: AgentDependencyAnalysis
    parallel_safety: AgentParallelSafetyAnalysis
    model: str = Field(min_length=1, max_length=120)
    prompt_token_count: int | None = Field(default=None, ge=0)
    completion_token_count: int | None = Field(default=None, ge=0)
    planning_ms: int = Field(ge=0)
