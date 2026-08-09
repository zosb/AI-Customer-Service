import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  fetchAdminFeedback,
  fetchAdminFeedbackSummary,
  fetchAdminOverview,
  fetchAdminSessionDetail,
  fetchAdminSessions,
  fetchDailyQuestionTrend,
} from '@/api/admin'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type {
  AdminFeedback,
  AdminFeedbackSummary,
  AdminOverview,
  AdminSession,
  AdminSessionDetail,
  DailyQuestionTrend,
} from '@/types/admin'

export const useAdminStore = defineStore('admin', () => {
  const auth = useAuthStore()
  const overview = ref<AdminOverview | null>(null)
  const trend = ref<DailyQuestionTrend | null>(null)
  const sessions = ref<AdminSession[]>([])
  const sessionTotal = ref(0)
  const sessionOffset = ref(0)
  const sessionLimit = 20
  const feedbackSummary = ref<AdminFeedbackSummary | null>(null)
  const feedback = ref<AdminFeedback[]>([])
  const selectedSession = ref<AdminSessionDetail | null>(null)
  const loading = ref(false)
  const loadingSession = ref(false)

  function requireToken(): string {
    if (!auth.token) {
      throw new ApiError(401, '登录状态已失效，请重新登录')
    }
    return auth.token
  }

  async function initialize(): Promise<void> {
    loading.value = true
    try {
      const token = requireToken()
      const [overviewResult, trendResult, sessionResult, summaryResult, feedbackResult] =
        await Promise.all([
          fetchAdminOverview(token),
          fetchDailyQuestionTrend(token, 14),
          fetchAdminSessions(token, sessionLimit, 0),
          fetchAdminFeedbackSummary(token),
          fetchAdminFeedback(token, 10, 0),
        ])
      overview.value = overviewResult
      trend.value = trendResult
      sessions.value = sessionResult.items
      sessionTotal.value = sessionResult.total
      sessionOffset.value = 0
      feedbackSummary.value = summaryResult
      feedback.value = feedbackResult.items
    } finally {
      loading.value = false
    }
  }

  async function loadSessionPage(offset: number, query = ''): Promise<void> {
    const safeOffset = Math.max(offset, 0)
    const result = await fetchAdminSessions(
      requireToken(),
      sessionLimit,
      safeOffset,
      query,
    )
    sessions.value = result.items
    sessionTotal.value = result.total
    sessionOffset.value = result.offset
  }

  async function openSession(sessionId: number): Promise<void> {
    loadingSession.value = true
    try {
      selectedSession.value = await fetchAdminSessionDetail(
        sessionId,
        requireToken(),
      )
    } finally {
      loadingSession.value = false
    }
  }

  function closeSession(): void {
    selectedSession.value = null
  }

  function reset(): void {
    overview.value = null
    trend.value = null
    sessions.value = []
    sessionTotal.value = 0
    sessionOffset.value = 0
    feedbackSummary.value = null
    feedback.value = []
    selectedSession.value = null
    loading.value = false
    loadingSession.value = false
  }

  return {
    overview,
    trend,
    sessions,
    sessionTotal,
    sessionOffset,
    sessionLimit,
    feedbackSummary,
    feedback,
    selectedSession,
    loading,
    loadingSession,
    initialize,
    loadSessionPage,
    openSession,
    closeSession,
    reset,
  }
})
