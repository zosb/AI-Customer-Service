import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as chatApi from '@/api/chat'
import { useChatStore } from '@/stores/chat'
import type { ChatSession } from '@/types/chat'

const archivedSession: ChatSession = {
  id: 21,
  user_id: 7,
  title: '历史退款咨询',
  status: 'archived',
  selected_knowledge_base_id: null,
  last_message_at: '2026-08-08T06:00:00Z',
  created_at: '2026-08-08T04:00:00Z',
  updated_at: '2026-08-08T06:00:00Z',
}

describe('chat archive center selection', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('ai_customer_service_access_token', 'test-token')
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('automatically opens the first archived session after entering archive mode', async () => {
    vi.spyOn(chatApi, 'listChatSessions').mockResolvedValue({
      items: [archivedSession],
      total: 1,
      limit: 100,
      offset: 0,
    })
    const historySpy = vi.spyOn(chatApi, 'getChatHistory').mockResolvedValue({
      session: archivedSession,
      messages: [],
    })
    vi.spyOn(chatApi, 'listSessionFeedback').mockResolvedValue([])

    const store = useChatStore()
    await store.showArchivedSessions()

    expect(store.sessionMode).toBe('archived')
    expect(store.activeSessionId).toBe(21)
    expect(store.activeSession?.status).toBe('archived')
    expect(historySpy).toHaveBeenCalledWith(21, 'test-token')
  })
})
