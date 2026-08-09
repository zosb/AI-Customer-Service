import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  listChatSessions,
  restoreChatSession,
} from '@/api/chat'


afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
    },
  })
}

function sessionPayload(status: 'active' | 'archived') {
  return {
    id: 21,
    user_id: 7,
    title: '历史退款咨询',
    status,
    selected_knowledge_base_id: null,
    last_message_at: '2026-08-08T05:00:00Z',
    created_at: '2026-08-08T04:00:00Z',
    updated_at: '2026-08-08T06:00:00Z',
  }
}


describe('chat session archive history api', () => {
  it('loads archived sessions with an explicit status filter', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        items: [sessionPayload('archived')],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    )

    const result = await listChatSessions('jwt-token', 'archived')

    expect(result.items[0]?.status).toBe('archived')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('status=archived'),
      expect.any(Object),
    )
  })

  it('restores an archived session through the dedicated endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(sessionPayload('active')),
    )

    const result = await restoreChatSession(21, 'jwt-token')

    expect(result.status).toBe('active')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/chat/sessions/21/restore'),
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
