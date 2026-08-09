export interface AgentPlanRequest {
  requirement: string
  system_context: string
}

export interface AgentServiceImpact {
  name: string
  reason: string
  change_scope: string[]
}

export interface AgentTaskDraft {
  id: string
  title: string
  service: string
  description: string
  depends_on: string[]
  acceptance_criteria: string[]
}

export interface AgentPlanDraft {
  requirement_summary: string
  services: AgentServiceImpact[]
  tasks: AgentTaskDraft[]
  assumptions: string[]
  risks: string[]
}

export interface AgentDependencyEdge {
  source: string
  target: string
}

export interface AgentExecutionStage {
  index: number
  task_ids: string[]
  parallel_candidate: boolean
}

export interface AgentDependencyAnalysis {
  total_tasks: number
  edges: AgentDependencyEdge[]
  topological_order: string[]
  stages: AgentExecutionStage[]
  root_tasks: string[]
  terminal_tasks: string[]
  critical_path: string[]
  max_parallelism: number
}

export interface AgentTaskResourceProfile {
  task_id: string
  service: string
  resources: string[]
}

export interface AgentResourceConflict {
  stage_index: number
  task_a: string
  task_b: string
  shared_resources: string[]
  reason: string
}

export interface AgentSafeExecutionBatch {
  stage_index: number
  batch_index: number
  task_ids: string[]
  parallel_safe: boolean
}

export interface AgentParallelSafetyAnalysis {
  total_tasks: number
  candidate_parallel_stages: number
  task_resources: AgentTaskResourceProfile[]
  conflicts: AgentResourceConflict[]
  batches: AgentSafeExecutionBatch[]
  max_safe_parallelism: number
}

export interface AgentPlanResponse {
  plan: AgentPlanDraft
  dependency: AgentDependencyAnalysis
  parallel_safety: AgentParallelSafetyAnalysis
  model: string
  prompt_token_count: number | null
  completion_token_count: number | null
  planning_ms: number
}
