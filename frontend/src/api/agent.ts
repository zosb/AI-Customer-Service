import { requestJson } from '@/api/http'
import type {
  AgentPlanRequest,
  AgentPlanResponse,
} from '@/types/agent'

export function createAgentPlan(
  payload: AgentPlanRequest,
  token: string,
): Promise<AgentPlanResponse> {
  return requestJson<AgentPlanResponse>(
    '/api/v1/agent/plans',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    token,
  )
}
