import { requestJson } from '@/api/http'
import type {
  AdminFeedbackListResponse,
  AdminFeedbackSummary,
  AdminOverview,
  AdminSessionDetail,
  AdminSessionListResponse,
  DailyQuestionTrend,
} from '@/types/admin'

export function fetchAdminOverview(token: string): Promise<AdminOverview> {
  return requestJson<AdminOverview>('/api/v1/admin/overview', {}, token)
}

export function fetchAdminSessions(
  token: string,
  limit = 20,
  offset = 0,
  query = '',
): Promise<AdminSessionListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  if (query.trim()) {
    params.set('q', query.trim())
  }
  return requestJson<AdminSessionListResponse>(
    `/api/v1/admin/sessions?${params.toString()}`,
    {},
    token,
  )
}

export function fetchAdminSessionDetail(
  sessionId: number,
  token: string,
): Promise<AdminSessionDetail> {
  return requestJson<AdminSessionDetail>(
    `/api/v1/admin/sessions/${sessionId}`,
    {},
    token,
  )
}

export function fetchAdminFeedbackSummary(
  token: string,
): Promise<AdminFeedbackSummary> {
  return requestJson<AdminFeedbackSummary>(
    '/api/v1/admin/feedback/summary',
    {},
    token,
  )
}

export function fetchAdminFeedback(
  token: string,
  limit = 10,
  offset = 0,
): Promise<AdminFeedbackListResponse> {
  return requestJson<AdminFeedbackListResponse>(
    `/api/v1/admin/feedback?limit=${limit}&offset=${offset}`,
    {},
    token,
  )
}

export function fetchDailyQuestionTrend(
  token: string,
  days = 14,
): Promise<DailyQuestionTrend> {
  return requestJson<DailyQuestionTrend>(
    `/api/v1/admin/analytics/daily-questions?days=${days}`,
    {},
    token,
  )
}
