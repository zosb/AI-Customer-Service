import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAgentPlan } from '@/api/agent'

afterEach(() => {
  vi.unstubAllGlobals()
})

function mockJson(payload: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

describe('agent api', () => {
  it('posts requirement and system context to agent endpoint', async () => {
    mockJson({
      plan: {
        requirement_summary: 'summary',
        services: [],
        tasks: [],
        assumptions: [],
        risks: [],
      },
      dependency: {
        total_tasks: 1,
        edges: [],
        topological_order: ['T1'],
        stages: [],
        root_tasks: ['T1'],
        terminal_tasks: ['T1'],
        critical_path: ['T1'],
        max_parallelism: 1,
      },
      parallel_safety: {
        total_tasks: 1,
        candidate_parallel_stages: 0,
        task_resources: [],
        conflicts: [],
        batches: [],
        max_safe_parallelism: 1,
      },
      model: 'qwen3.5:4b',
      prompt_token_count: 10,
      completion_token_count: 20,
      planning_ms: 100,
    })

    await createAgentPlan(
      {
        requirement: '需求',
        system_context: '系统文档',
      },
      'token-1',
    )

    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(String(url)).toContain('/api/v1/agent/plans')
    expect(init).toBeDefined()
    expect(init?.method).toBe('POST')

    const headers = new Headers(init?.headers)
    expect(headers.get('Authorization')).toBe('Bearer token-1')

    const body = JSON.parse(String(init?.body)) as {
      requirement: string
      system_context: string
    }
    expect(body.requirement).toBe('需求')
    expect(body.system_context).toBe('系统文档')
  })
})
