from __future__ import annotations

from app.schemas.agent import AgentPlanDraft
from app.services.agent.dependency_graph import AgentDependencyGraph
from app.services.agent.resource_safety import AgentResourceSafetyAnalyzer


def make_plan(rows: list[dict]) -> AgentPlanDraft:
    services = sorted({row["service"] for row in rows})
    return AgentPlanDraft.model_validate(
        {
            "requirement_summary": "并行安全测试",
            "services": [
                {
                    "name": name,
                    "reason": "测试服务",
                    "change_scope": ["module"],
                }
                for name in services
            ],
            "tasks": [
                {
                    "id": row["id"],
                    "title": row.get("title", row["id"]),
                    "service": row["service"],
                    "description": row["description"],
                    "depends_on": row.get("depends_on", []),
                    "acceptance_criteria": row.get("acceptance_criteria", ["done"]),
                }
                for row in rows
            ],
            "assumptions": [],
            "risks": [],
        }
    )


def analyze(rows: list[dict]):
    plan = make_plan(rows)
    dag = AgentDependencyGraph().analyze(plan)
    return AgentResourceSafetyAnalyzer().analyze(plan=plan, dependency=dag)


def test_independent_cross_service_tasks_share_safe_batch() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "gateway", "description": "准备 contract", "depends_on": []},
            {"id": "T2", "service": "order-service", "description": "修改 order_archive 表", "depends_on": ["T1"]},
            {"id": "T3", "service": "notification-service", "description": "修改 sms_template 表", "depends_on": ["T1"]},
        ]
    )
    stage2 = [b for b in result.batches if b.stage_index == 2]
    assert len(stage2) == 1
    assert stage2[0].task_ids == ["T2", "T3"]
    assert stage2[0].parallel_safe is True
    assert result.max_safe_parallelism == 2


def test_shared_table_splits_same_stage_into_separate_batches() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "svc", "description": "准备", "depends_on": []},
            {"id": "T2", "service": "svc", "description": "新增 notification_delivery 表索引", "depends_on": ["T1"]},
            {"id": "T3", "service": "svc", "description": "修改 notification_delivery 表状态列", "depends_on": ["T1"]},
        ]
    )
    assert any("table:notification_delivery" in c.shared_resources for c in result.conflicts)
    stage2 = [b for b in result.batches if b.stage_index == 2]
    assert [b.task_ids for b in stage2] == [["T2"], ["T3"]]


def test_shared_api_contract_conflicts_even_across_services() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "svc-a", "description": "调整 POST /orders 请求契约"},
            {"id": "T2", "service": "svc-b", "description": "同步适配 GET /orders 契约"},
        ]
    )
    assert len(result.conflicts) == 1
    assert "api:/orders" in result.conflicts[0].shared_resources


def test_shared_event_contract_conflicts_across_services() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "order-service", "description": "定义 OrderCreated 事件字段"},
            {"id": "T2", "service": "notification-service", "description": "修改 OrderCreated 事件解析"},
        ]
    )
    assert "event:ordercreated" in result.conflicts[0].shared_resources


def test_same_service_unknown_scope_is_conservatively_serialized() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "svc", "description": "重构核心业务流程"},
            {"id": "T2", "service": "svc", "description": "优化错误处理"},
        ]
    )
    assert result.conflicts[0].shared_resources == ["service-unknown:svc"]
    assert result.max_safe_parallelism == 1


def test_same_service_distinct_explicit_resources_can_parallel() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "svc", "description": "修改 order_archive 表"},
            {"id": "T2", "service": "svc", "description": "修改 notification_delivery 表"},
        ]
    )
    assert result.conflicts == []
    assert result.max_safe_parallelism == 2


def test_same_file_path_conflicts() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "svc-a", "description": "修改 app/contracts/order.py"},
            {"id": "T2", "service": "svc-b", "description": "同步 app/contracts/order.py"},
        ]
    )
    assert "file:app/contracts/order.py" in result.conflicts[0].shared_resources


def test_shared_topic_conflicts() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "svc-a", "description": "创建 Topic order.created"},
            {"id": "T2", "service": "svc-b", "description": "调整 Topic order.created 分区"},
        ]
    )
    assert "topic:order.created" in result.conflicts[0].shared_resources


def test_linear_dag_keeps_one_task_per_batch() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "a", "description": "修改 a_table 表"},
            {"id": "T2", "service": "b", "description": "修改 b_table 表", "depends_on": ["T1"]},
            {"id": "T3", "service": "c", "description": "修改 c_table 表", "depends_on": ["T2"]},
        ]
    )
    assert [b.task_ids for b in result.batches] == [["T1"], ["T2"], ["T3"]]


def test_greedy_batches_preserve_non_conflicting_pair() -> None:
    result = analyze(
        [
            {"id": "T1", "service": "a", "description": "修改 shared_table 表"},
            {"id": "T2", "service": "b", "description": "修改 shared_table 表"},
            {"id": "T3", "service": "c", "description": "修改 isolated_table 表"},
        ]
    )
    # T1/T2 冲突，但 T3 可以与 T1 同批。
    assert [b.task_ids for b in result.batches] == [["T1", "T3"], ["T2"]]
    assert result.max_safe_parallelism == 2


def test_every_task_appears_once_in_safe_batches() -> None:
    rows = [
        {"id": "T1", "service": "a", "description": "修改 x_table 表"},
        {"id": "T2", "service": "b", "description": "修改 x_table 表"},
        {"id": "T3", "service": "c", "description": "修改 y_table 表"},
        {"id": "T4", "service": "d", "description": "修改 z_table 表", "depends_on": ["T1", "T2"]},
    ]
    result = analyze(rows)
    flattened = [task_id for batch in result.batches for task_id in batch.task_ids]
    assert sorted(flattened) == ["T1", "T2", "T3", "T4"]
    assert len(flattened) == len(set(flattened))
