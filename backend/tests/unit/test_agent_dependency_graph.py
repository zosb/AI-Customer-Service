from __future__ import annotations

import pytest

from app.schemas.agent import AgentPlanDraft
from app.services.agent.dependency_graph import (
    AgentDependencyGraph,
    AgentDependencyGraphError,
)


def make_plan(task_rows: list[tuple[str, list[str]]]) -> AgentPlanDraft:
    return AgentPlanDraft.model_validate(
        {
            "requirement_summary": "测试依赖图",
            "services": [
                {
                    "name": "svc",
                    "reason": "测试",
                    "change_scope": ["module"],
                }
            ],
            "tasks": [
                {
                    "id": task_id,
                    "title": task_id,
                    "service": "svc",
                    "description": f"execute {task_id}",
                    "depends_on": depends_on,
                    "acceptance_criteria": [f"{task_id} done"],
                }
                for task_id, depends_on in task_rows
            ],
            "assumptions": [],
            "risks": [],
        }
    )


def test_linear_plan_produces_one_task_per_stage() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", ["T1"]),
            ("T3", ["T2"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    assert result.topological_order == ["T1", "T2", "T3"]
    assert [stage.task_ids for stage in result.stages] == [
        ["T1"],
        ["T2"],
        ["T3"],
    ]
    assert result.max_parallelism == 1
    assert result.critical_path == ["T1", "T2", "T3"]


def test_branching_tasks_become_parallel_candidates() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", ["T1"]),
            ("T3", ["T1"]),
            ("T4", ["T2", "T3"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    assert [stage.task_ids for stage in result.stages] == [
        ["T1"],
        ["T2", "T3"],
        ["T4"],
    ]
    assert result.stages[1].parallel_candidate is True
    assert result.max_parallelism == 2


def test_multiple_roots_share_first_stage() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", []),
            ("T3", ["T1", "T2"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    assert result.root_tasks == ["T1", "T2"]
    assert result.stages[0].task_ids == ["T1", "T2"]
    assert result.terminal_tasks == ["T3"]


def test_edges_are_dependency_to_dependent() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", ["T1"]),
            ("T3", ["T1", "T2"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    assert [
        (edge.source, edge.target)
        for edge in result.edges
    ] == [
        ("T1", "T2"),
        ("T1", "T3"),
        ("T2", "T3"),
    ]


def test_numeric_task_order_is_stable() -> None:
    plan = make_plan(
        [
            ("T10", []),
            ("T2", []),
            ("T1", []),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    assert result.topological_order == ["T1", "T2", "T10"]


def test_critical_path_picks_longest_dependency_chain() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", ["T1"]),
            ("T3", ["T1"]),
            ("T4", ["T2"]),
            ("T5", ["T4"]),
            ("T6", ["T3"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    assert result.critical_path == ["T1", "T2", "T4", "T5"]


def test_cycle_is_rejected() -> None:
    plan = make_plan(
        [
            ("T1", ["T3"]),
            ("T2", ["T1"]),
            ("T3", ["T2"]),
        ]
    )

    with pytest.raises(
        AgentDependencyGraphError,
        match="循环",
    ):
        AgentDependencyGraph().analyze(plan)


def test_diamond_graph_merges_only_after_both_parents_complete() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", ["T1"]),
            ("T3", ["T1"]),
            ("T4", ["T2", "T3"]),
            ("T5", ["T4"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)

    stage_by_task = {
        task_id: stage.index
        for stage in result.stages
        for task_id in stage.task_ids
    }
    assert stage_by_task["T2"] == stage_by_task["T3"] == 2
    assert stage_by_task["T4"] == 3
    assert stage_by_task["T5"] == 4


def test_every_dependency_precedes_task_in_topological_order() -> None:
    plan = make_plan(
        [
            ("T1", []),
            ("T2", ["T1"]),
            ("T3", ["T1"]),
            ("T4", ["T2"]),
            ("T5", ["T2", "T3"]),
        ]
    )

    result = AgentDependencyGraph().analyze(plan)
    position = {
        task_id: index
        for index, task_id in enumerate(result.topological_order)
    }

    for task in plan.tasks:
        for dependency in task.depends_on:
            assert position[dependency] < position[task.id]
