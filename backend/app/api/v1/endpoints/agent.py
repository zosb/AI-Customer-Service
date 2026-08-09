from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AgentExecutionPlanServiceDep, CurrentAdmin
from app.schemas.agent import AgentPlanRequest, AgentPlanResponse
from app.services.agent.dependency_graph import AgentDependencyGraphError
from app.services.agent.planner import AgentPlanningError
from app.services.agent.resource_safety import AgentResourceSafetyError

router = APIRouter(
    prefix="/agent",
    tags=["AI Agent"],
)


@router.post(
    "/plans",
    response_model=AgentPlanResponse,
    summary="生成多微服务研发执行计划",
    description=(
        "管理员提交用户需求和系统技术/接口文档后，系统使用本地 Ollama "
        "Planner 拆解受影响微服务与原子任务，再执行 DAG 拓扑分析和资源冲突检查，"
        "返回安全执行批次。"
    ),
)
def create_agent_plan(
    payload: AgentPlanRequest,
    current_admin: CurrentAdmin,
    service: AgentExecutionPlanServiceDep,
) -> AgentPlanResponse:
    del current_admin
    try:
        result = service.create_plan(
            requirement=payload.requirement,
            system_context=payload.system_context,
        )
    except AgentPlanningError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent Planner 生成失败：{exc}",
        ) from exc
    except (AgentDependencyGraphError, AgentResourceSafetyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Agent 执行计划无法通过安全校验：{exc}",
        ) from exc

    return AgentPlanResponse(
        plan=result.plan,
        dependency=result.dependency,
        parallel_safety=result.parallel_safety,
        model=result.model,
        prompt_token_count=result.prompt_token_count,
        completion_token_count=result.completion_token_count,
        planning_ms=result.planning_ms,
    )
