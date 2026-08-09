import { ref } from 'vue'
import { defineStore } from 'pinia'

import { createAgentPlan } from '@/api/agent'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type {
  AgentPlanRequest,
  AgentPlanResponse,
} from '@/types/agent'

export const useAgentStore = defineStore('agent', () => {
  const auth = useAuthStore()
  const result = ref<AgentPlanResponse | null>(null)
  const loading = ref(false)

  function requireAdminToken(): string {
    if (!auth.token) {
      throw new ApiError(401, '登录状态已失效，请重新登录')
    }
    if (auth.user?.role !== 'admin') {
      throw new ApiError(403, '仅管理员可以使用 AI Agent Planner')
    }
    return auth.token
  }

  async function generate(payload: AgentPlanRequest): Promise<void> {
    loading.value = true
    try {
      result.value = await createAgentPlan(
        payload,
        requireAdminToken(),
      )
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    result.value = null
    loading.value = false
  }

  return {
    result,
    loading,
    generate,
    reset,
  }
})
