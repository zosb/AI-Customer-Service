from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from app.schemas.agent import (
    AgentDependencyAnalysis,
    AgentParallelSafetyAnalysis,
    AgentPlanDraft,
)
from app.services.agent.dependency_graph import AgentDependencyGraph
from app.services.agent.planner import AgentPlanner, AgentPlanningResult
from app.services.agent.resource_safety import AgentResourceSafetyAnalyzer


@dataclass(frozen=True)
class AgentExecutionPlanResult:
    """Planner + DAG + 资源安全分析的完整执行计划。"""

    plan: AgentPlanDraft
    dependency: AgentDependencyAnalysis
    parallel_safety: AgentParallelSafetyAnalysis
    model: str
    prompt_token_count: int | None
    completion_token_count: int | None
    planning_ms: int


class AgentExecutionPlanService:
    """组合 Planner、依赖图和资源安全分析，形成稳定的应用服务。"""

    def __init__(
        self,
        *,
        planner: AgentPlanner | None = None,
        dependency_graph: AgentDependencyGraph | None = None,
        resource_safety: AgentResourceSafetyAnalyzer | None = None,
    ) -> None:
        self.planner = planner or AgentPlanner()
        self.dependency_graph = dependency_graph or AgentDependencyGraph()
        self.resource_safety = resource_safety or AgentResourceSafetyAnalyzer()

    def create_plan(
        self,
        *,
        requirement: str,
        system_context: str,
    ) -> AgentExecutionPlanResult:
        started = perf_counter()
        planner_result: AgentPlanningResult = self.planner.plan(
            requirement=requirement,
            system_context=system_context,
        )
        dependency = self.dependency_graph.analyze(planner_result.plan)
        parallel_safety = self.resource_safety.analyze(
            plan=planner_result.plan,
            dependency=dependency,
        )
        elapsed_ms = max(0, int((perf_counter() - started) * 1000))

        return AgentExecutionPlanResult(
            plan=planner_result.plan,
            dependency=dependency,
            parallel_safety=parallel_safety,
            model=planner_result.model,
            prompt_token_count=planner_result.prompt_token_count,
            completion_token_count=planner_result.completion_token_count,
            planning_ms=elapsed_ms,
        )
