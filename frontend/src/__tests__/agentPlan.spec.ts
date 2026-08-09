import { describe, expect, it } from 'vitest'

import {
  formatPlanningDuration,
  groupSafeBatches,
  indexTasks,
  totalTokenCount,
} from '@/utils/agentPlan'
import type { AgentPlanResponse } from '@/types/agent'

function makeResponse(): AgentPlanResponse {
  return {
    plan: {
      requirement_summary: 'summary',
      services: [
        {
          name: 'order-service',
          reason: 'reason',
          change_scope: ['api'],
        },
      ],
      tasks: [
        {
          id: 'T1',
          title: '任务1',
          service: 'order-service',
          description: 'desc',
          depends_on: [],
          acceptance_criteria: ['pass'],
        },
        {
          id: 'T2',
          title: '任务2',
          service: 'order-service',
          description: 'desc',
          depends_on: ['T1'],
          acceptance_criteria: ['pass'],
        },
      ],
      assumptions: [],
      risks: [],
    },
    dependency: {
      total_tasks: 2,
      edges: [{ source: 'T1', target: 'T2' }],
      topological_order: ['T1', 'T2'],
      stages: [
        { index: 1, task_ids: ['T1'], parallel_candidate: false },
        { index: 2, task_ids: ['T2'], parallel_candidate: false },
      ],
      root_tasks: ['T1'],
      terminal_tasks: ['T2'],
      critical_path: ['T1', 'T2'],
      max_parallelism: 1,
    },
    parallel_safety: {
      total_tasks: 2,
      candidate_parallel_stages: 0,
      task_resources: [],
      conflicts: [],
      batches: [
        {
          stage_index: 2,
          batch_index: 2,
          task_ids: ['T2'],
          parallel_safe: false,
        },
        {
          stage_index: 1,
          batch_index: 1,
          task_ids: ['T1'],
          parallel_safe: false,
        },
      ],
      max_safe_parallelism: 1,
    },
    model: 'qwen3.5:4b',
    prompt_token_count: 20,
    completion_token_count: 30,
    planning_ms: 76628,
  }
}

describe('agent plan utils', () => {
  it('indexes tasks by id', () => {
    const indexed = indexTasks(makeResponse())
    expect(indexed.T2?.depends_on).toEqual(['T1'])
  })

  it('groups safe batches by sorted stage', () => {
    const groups = groupSafeBatches(makeResponse())
    expect(groups.map((item) => item.stageIndex)).toEqual([1, 2])
    expect(groups[0]?.batches[0]?.task_ids).toEqual(['T1'])
  })

  it('formats millisecond, second and minute durations', () => {
    expect(formatPlanningDuration(800)).toBe('800 ms')
    expect(formatPlanningDuration(15000)).toBe('15.0 s')
    expect(formatPlanningDuration(76628)).toBe('1m 17s')
  })

  it('adds prompt and completion token counts safely', () => {
    expect(totalTokenCount(makeResponse())).toBe(50)
  })

  it('handles null response', () => {
    expect(indexTasks(null)).toEqual({})
    expect(groupSafeBatches(null)).toEqual([])
    expect(totalTokenCount(null)).toBe(0)
  })
})
