import type {
  AgentPlanResponse,
  AgentSafeExecutionBatch,
  AgentTaskDraft,
} from '@/types/agent'

export interface AgentStageBatchGroup {
  stageIndex: number
  batches: AgentSafeExecutionBatch[]
}

export function indexTasks(
  response: AgentPlanResponse | null,
): Record<string, AgentTaskDraft> {
  const result: Record<string, AgentTaskDraft> = {}
  for (const task of response?.plan.tasks ?? []) {
    result[task.id] = task
  }
  return result
}

export function groupSafeBatches(
  response: AgentPlanResponse | null,
): AgentStageBatchGroup[] {
  const groups = new Map<number, AgentSafeExecutionBatch[]>()

  for (const batch of response?.parallel_safety.batches ?? []) {
    const current = groups.get(batch.stage_index) ?? []
    current.push(batch)
    groups.set(batch.stage_index, current)
  }

  return [...groups.entries()]
    .sort(([left], [right]) => left - right)
    .map(([stageIndex, batches]) => ({
      stageIndex,
      batches: [...batches].sort(
        (left, right) => left.batch_index - right.batch_index,
      ),
    }))
}

export function formatPlanningDuration(milliseconds: number): string {
  if (milliseconds < 1000) {
    return `${milliseconds} ms`
  }

  const seconds = milliseconds / 1000
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`
  }

  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  return `${minutes}m ${remainder}s`
}

export function totalTokenCount(
  response: AgentPlanResponse | null,
): number {
  if (!response) {
    return 0
  }
  return (
    (response.prompt_token_count ?? 0) +
    (response.completion_token_count ?? 0)
  )
}
