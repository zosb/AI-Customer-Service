from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.schemas.agent import (
    AgentDependencyAnalysis,
    AgentDependencyEdge,
    AgentExecutionStage,
    AgentPlanDraft,
)


class AgentDependencyGraphError(RuntimeError):
    """Agent 任务依赖图无法形成合法 DAG。"""


def _task_sort_key(task_id: str) -> tuple[int, str]:
    try:
        return (int(task_id[1:]), task_id)
    except (TypeError, ValueError):
        return (10**9, str(task_id))


@dataclass(frozen=True)
class _CriticalState:
    length: int
    previous: str | None


class AgentDependencyGraph:
    """
    将 AgentPlanDraft 的直接 depends_on 关系转换为可执行 DAG 分析结果。

    本组件只回答“依赖拓扑上哪些任务可同时开始”。
    同一拓扑层中的任务仅是 parallel_candidate；文件/数据库/接口资源冲突
    由资源安全组件继续执行二次并行校验。
    """

    def analyze(self, plan: AgentPlanDraft) -> AgentDependencyAnalysis:
        task_ids = [task.id for task in plan.tasks]
        task_set = set(task_ids)
        if not task_ids:
            raise AgentDependencyGraphError("Agent 计划没有可分析任务")

        dependencies: dict[str, set[str]] = {}
        dependents: dict[str, set[str]] = defaultdict(set)
        edges: list[AgentDependencyEdge] = []

        for task in plan.tasks:
            direct_dependencies = set(task.depends_on)
            unknown = direct_dependencies - task_set
            if unknown:
                raise AgentDependencyGraphError(
                    f"任务 {task.id} 存在未知依赖：{sorted(unknown, key=_task_sort_key)}"
                )
            if task.id in direct_dependencies:
                raise AgentDependencyGraphError(
                    f"任务 {task.id} 不能依赖自身"
                )

            dependencies[task.id] = direct_dependencies
            for dependency in direct_dependencies:
                dependents[dependency].add(task.id)
                edges.append(
                    AgentDependencyEdge(
                        source=dependency,
                        target=task.id,
                    )
                )

        edges.sort(
            key=lambda edge: (
                _task_sort_key(edge.source),
                _task_sort_key(edge.target),
            )
        )

        indegree = {
            task_id: len(dependencies[task_id])
            for task_id in task_ids
        }
        ready = sorted(
            [task_id for task_id, degree in indegree.items() if degree == 0],
            key=_task_sort_key,
        )

        stages: list[AgentExecutionStage] = []
        topological_order: list[str] = []

        while ready:
            current_stage = list(ready)
            stages.append(
                AgentExecutionStage(
                    index=len(stages) + 1,
                    task_ids=current_stage,
                    parallel_candidate=len(current_stage) > 1,
                )
            )
            topological_order.extend(current_stage)

            next_ready: list[str] = []
            for task_id in current_stage:
                for child in sorted(
                    dependents.get(task_id, set()),
                    key=_task_sort_key,
                ):
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        next_ready.append(child)

            ready = sorted(set(next_ready), key=_task_sort_key)

        if len(topological_order) != len(task_ids):
            blocked = sorted(
                [
                    task_id
                    for task_id, degree in indegree.items()
                    if degree > 0
                ],
                key=_task_sort_key,
            )
            raise AgentDependencyGraphError(
                "任务依赖存在循环，无法形成 DAG；"
                f"循环相关任务：{blocked}"
            )

        root_tasks = sorted(
            [
                task_id
                for task_id in task_ids
                if not dependencies[task_id]
            ],
            key=_task_sort_key,
        )
        terminal_tasks = sorted(
            [
                task_id
                for task_id in task_ids
                if not dependents.get(task_id)
            ],
            key=_task_sort_key,
        )

        critical_path = self._critical_path(
            topological_order=topological_order,
            dependencies=dependencies,
        )

        return AgentDependencyAnalysis(
            total_tasks=len(task_ids),
            edges=edges,
            topological_order=topological_order,
            stages=stages,
            root_tasks=root_tasks,
            terminal_tasks=terminal_tasks,
            critical_path=critical_path,
            max_parallelism=max(len(stage.task_ids) for stage in stages),
        )

    @staticmethod
    def _critical_path(
        *,
        topological_order: list[str],
        dependencies: dict[str, set[str]],
    ) -> list[str]:
        states: dict[str, _CriticalState] = {}

        for task_id in topological_order:
            parents = sorted(
                dependencies[task_id],
                key=_task_sort_key,
            )
            if not parents:
                states[task_id] = _CriticalState(
                    length=1,
                    previous=None,
                )
                continue

            best_parent = max(
                parents,
                key=lambda parent: (
                    states[parent].length,
                    -_task_sort_key(parent)[0],
                ),
            )
            states[task_id] = _CriticalState(
                length=states[best_parent].length + 1,
                previous=best_parent,
            )

        end_task = max(
            topological_order,
            key=lambda task_id: (
                states[task_id].length,
                -_task_sort_key(task_id)[0],
            ),
        )

        result: list[str] = []
        cursor: str | None = end_task
        while cursor is not None:
            result.append(cursor)
            cursor = states[cursor].previous

        result.reverse()
        return result
