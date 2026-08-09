from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from app.schemas.agent import (
    AgentDependencyAnalysis,
    AgentParallelSafetyAnalysis,
    AgentPlanDraft,
    AgentResourceConflict,
    AgentSafeExecutionBatch,
    AgentTaskDraft,
    AgentTaskResourceProfile,
)


class AgentResourceSafetyError(RuntimeError):
    """资源安全分析无法可靠完成。"""


_API_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_./{}:\-]+)",
    re.IGNORECASE,
)
_FILE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|vue|sql|json|ya?ml))",
    re.IGNORECASE,
)
_TABLE_ZH_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_]{2,})\s*表",
    re.IGNORECASE,
)
_TABLE_EN_RE = re.compile(
    r"\btable\s*[:：]?\s*`?([A-Za-z][A-Za-z0-9_]{2,})`?",
    re.IGNORECASE,
)
_EVENT_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]*(?:Created|Updated|Deleted|Changed|Requested|Completed|Failed|Succeeded|Event))\b"
)
_TOPIC_RE = re.compile(
    r"\bTopic\s*[:：]?\s*`?([A-Za-z0-9_.-]{2,})`?",
    re.IGNORECASE,
)


def _task_sort_key(task_id: str) -> tuple[int, str]:
    try:
        return (int(task_id[1:]), task_id)
    except (TypeError, ValueError):
        return (10**9, str(task_id))


def _normalize_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    return normalized.lower()


@dataclass(frozen=True)
class _TaskResources:
    task_id: str
    service: str
    resources: frozenset[str]


class AgentResourceSafetyAnalyzer:
    """
    对 Dependency DAG 的“并行候选”做二次安全检查。

    原则：
    1. 共享文件、API Path、数据库表、事件 Contract、Kafka Topic 的任务不得并行；
    2. 同一服务内，如果任一任务无法提取出明确资源边界，则保守判定为冲突；
    3. 同一服务但双方资源明确且互不重叠，可以作为安全并行候选；
    4. 不改变 DAG 的跨 Stage 顺序，只在单个 Stage 内进一步拆 batch。
    """

    def analyze(
        self,
        *,
        plan: AgentPlanDraft,
        dependency: AgentDependencyAnalysis,
    ) -> AgentParallelSafetyAnalysis:
        task_by_id = {task.id: task for task in plan.tasks}
        if set(task_by_id) != set(dependency.topological_order):
            raise AgentResourceSafetyError(
                "DependencyAnalysis 与 AgentPlanDraft 的任务集合不一致"
            )

        resource_map: dict[str, _TaskResources] = {}
        profiles: list[AgentTaskResourceProfile] = []
        for task_id in sorted(task_by_id, key=_task_sort_key):
            task = task_by_id[task_id]
            resources = frozenset(self.extract_resources(task))
            resource_map[task_id] = _TaskResources(
                task_id=task_id,
                service=task.service,
                resources=resources,
            )
            profiles.append(
                AgentTaskResourceProfile(
                    task_id=task_id,
                    service=task.service,
                    resources=sorted(resources),
                )
            )

        conflicts: list[AgentResourceConflict] = []
        conflict_pairs: set[frozenset[str]] = set()

        for stage in dependency.stages:
            for task_a, task_b in combinations(stage.task_ids, 2):
                conflict = self._pair_conflict(
                    stage_index=stage.index,
                    left=resource_map[task_a],
                    right=resource_map[task_b],
                )
                if conflict is None:
                    continue
                conflicts.append(conflict)
                conflict_pairs.add(frozenset((task_a, task_b)))

        conflicts.sort(
            key=lambda item: (
                item.stage_index,
                _task_sort_key(item.task_a),
                _task_sort_key(item.task_b),
            )
        )

        batches: list[AgentSafeExecutionBatch] = []
        for stage in dependency.stages:
            stage_batches: list[list[str]] = []
            for task_id in sorted(stage.task_ids, key=_task_sort_key):
                placed = False
                for batch in stage_batches:
                    if all(
                        frozenset((task_id, member)) not in conflict_pairs
                        for member in batch
                    ):
                        batch.append(task_id)
                        placed = True
                        break
                if not placed:
                    stage_batches.append([task_id])

            for batch_index, task_ids in enumerate(stage_batches, start=1):
                batches.append(
                    AgentSafeExecutionBatch(
                        stage_index=stage.index,
                        batch_index=batch_index,
                        task_ids=task_ids,
                        parallel_safe=len(task_ids) > 1,
                    )
                )

        return AgentParallelSafetyAnalysis(
            total_tasks=len(task_by_id),
            candidate_parallel_stages=sum(
                1 for stage in dependency.stages if len(stage.task_ids) > 1
            ),
            task_resources=profiles,
            conflicts=conflicts,
            batches=batches,
            max_safe_parallelism=max(len(batch.task_ids) for batch in batches),
        )

    @classmethod
    def extract_resources(cls, task: AgentTaskDraft) -> list[str]:
        text = "\n".join(
            [
                task.title,
                task.description,
                *task.acceptance_criteria,
            ]
        )
        resources: set[str] = set()

        for method, path in _API_RE.findall(text):
            # API path 是共享 Contract；即便 method 不同，也先按 path 保守互斥。
            resources.add(f"api:{_normalize_path(path)}")

        for path in _FILE_RE.findall(text):
            resources.add(f"file:{_normalize_path(path)}")

        for table_name in _TABLE_ZH_RE.findall(text):
            resources.add(f"table:{table_name.lower()}")
        for table_name in _TABLE_EN_RE.findall(text):
            resources.add(f"table:{table_name.lower()}")

        for event_name in _EVENT_RE.findall(text):
            resources.add(f"event:{event_name.lower()}")

        for topic_name in _TOPIC_RE.findall(text):
            resources.add(f"topic:{topic_name.lower()}")

        # 未给出具体表名但明显属于 DB schema/migration 的任务，按服务级 schema 互斥。
        lower_text = text.lower()
        if (
            "migration" in lower_text
            or "ddl" in lower_text
            or "数据库迁移" in text
            or "表结构" in text
        ) and not any(item.startswith("table:") for item in resources):
            resources.add(f"db-schema:{task.service.lower()}")

        return sorted(resources)

    @staticmethod
    def _pair_conflict(
        *,
        stage_index: int,
        left: _TaskResources,
        right: _TaskResources,
    ) -> AgentResourceConflict | None:
        shared = sorted(left.resources & right.resources)
        if shared:
            return AgentResourceConflict(
                stage_index=stage_index,
                task_a=left.task_id,
                task_b=right.task_id,
                shared_resources=shared,
                reason="共享可写资源或接口/事件 Contract，不能在同一安全并行批次修改",
            )

        if left.service == right.service and (
            not left.resources or not right.resources
        ):
            synthetic = f"service-unknown:{left.service.lower()}"
            return AgentResourceConflict(
                stage_index=stage_index,
                task_a=left.task_id,
                task_b=right.task_id,
                shared_resources=[synthetic],
                reason=(
                    "两个任务属于同一微服务，但至少一个任务没有可确认的资源边界；"
                    "按安全优先策略串行执行"
                ),
            )

        return None
