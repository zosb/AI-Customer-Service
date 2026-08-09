import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAdminFeedbackSummary,
  fetchAdminOverview,
  fetchAdminSessions,
  fetchDailyQuestionTrend,
} from '@/api/admin'


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

describe('admin api', () => {
  it('loads overview with bearer token', async () => {
    mockJson({ total_users: 3 })
    await fetchAdminOverview('token-1')
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/admin/overview',
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    )
    const init = vi.mocked(fetch).mock.calls[0]?.[1]
    expect(init).toBeDefined()
    const headers = new Headers(init?.headers)
    expect(headers.get('Authorization')).toBe('Bearer token-1')
  })

  it('builds session pagination and search params', async () => {
    mockJson({ items: [], total: 0, limit: 20, offset: 20 })
    await fetchAdminSessions('token', 20, 20, '退款')
    const url = String(vi.mocked(fetch).mock.calls[0]?.[0])
    expect(url).toContain('/api/v1/admin/sessions?')
    expect(url).toContain('offset=20')
    expect(url).toContain('q=%E9%80%80%E6%AC%BE')
  })

  it('loads feedback summary', async () => {
    mockJson({ total: 0, positive: 0, negative: 0, satisfaction_rate: 0, by_intent: [] })
    const result = await fetchAdminFeedbackSummary('token')
    expect(result.total).toBe(0)
  })

  it('loads daily question trend', async () => {
    mockJson({ days: 7, total_questions: 2, average_per_day: 0.29, items: [] })
    const result = await fetchDailyQuestionTrend('token', 7)
    expect(result.days).toBe(7)
  })
})
