import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  archiveChatSession,
  createChatSession,
  getChatHistory,
  deleteMessageFeedback as deleteMessageFeedbackApi,
  getMessageSources,
  listChatSessions,
  listSessionFeedback,
  renameChatSession,
  restoreChatSession,
  streamChatAnswer,
  submitMessageFeedback as submitMessageFeedbackApi,
} from '@/api/chat'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type {
  ChatMessage,
  ChatSession,
  ChatSessionStatus,
  ChatStreamDone,
  FeedbackRating,
  MessageFeedback,
  MessageSource,
} from '@/types/chat'

let temporaryId = -1

function newTemporaryId(): number {
  return temporaryId--
}

function nowIso(): string {
  return new Date().toISOString()
}

export const useChatStore = defineStore('chat', () => {
  const auth = useAuthStore()

  const sessions = ref<ChatSession[]>([])
  const sessionMode = ref<ChatSessionStatus>('active')
  const activeSessionId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const sourcesByMessageId = ref<Record<number, MessageSource[]>>({})
  const feedbackByMessageId = ref<Record<number, MessageFeedback>>({})

  const loadingSessions = ref(false)
  const loadingMessages = ref(false)
  const streaming = ref(false)
  const streamText = ref('')
  const streamSources = ref<MessageSource[]>([])
  const streamError = ref('')
  const dailyQuestionCount = ref<number | null>(null)
  const currentIntent = ref<string | null>(null)
  const feedbackSubmittingMessageId = ref<number | null>(null)

  let activeController: AbortController | null = null

  const activeSession = computed(
    () =>
      sessions.value.find((item) => item.id === activeSessionId.value) ??
      null,
  )

  function requireToken(): string {
    if (!auth.token) {
      throw new ApiError(401, '登录状态已失效，请重新登录')
    }
    return auth.token
  }

  function clearConversationState(): void {
    activeSessionId.value = null
    messages.value = []
    sourcesByMessageId.value = {}
    feedbackByMessageId.value = {}
    currentIntent.value = null
    streamError.value = ''
    streamText.value = ''
    streamSources.value = []
  }

  async function loadSessions(
    status: ChatSessionStatus = sessionMode.value,
  ): Promise<void> {
    loadingSessions.value = true
    try {
      const result = await listChatSessions(requireToken(), status)
      sessionMode.value = status
      sessions.value = result.items

      if (
        activeSessionId.value !== null &&
        !sessions.value.some((item) => item.id === activeSessionId.value)
      ) {
        clearConversationState()
      }
    } finally {
      loadingSessions.value = false
    }
  }

  async function showRecentSessions(): Promise<void> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，请等待当前回答结束')
    }
    await loadSessions('active')
  }

  async function showArchivedSessions(): Promise<void> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，请等待当前回答结束')
    }

    await loadSessions('archived')

    const firstArchivedSession = sessions.value[0]
    if (firstArchivedSession && activeSessionId.value === null) {
      await openSession(firstArchivedSession.id)
    }
  }

  async function createSession(): Promise<ChatSession> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，请等待当前回答结束')
    }

    const session = await createChatSession(requireToken())

    if (sessionMode.value === 'active') {
      sessions.value = [session, ...sessions.value]
    } else {
      await loadSessions('active')
    }

    activeSessionId.value = session.id
    messages.value = []
    sourcesByMessageId.value = {}
    feedbackByMessageId.value = {}
    currentIntent.value = null
    return session
  }

  async function openSession(sessionId: number): Promise<void> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，请等待当前回答结束')
    }

    activeSessionId.value = sessionId
    loadingMessages.value = true
    streamError.value = ''

    try {
      const token = requireToken()
      const [history, feedback] = await Promise.all([
        getChatHistory(sessionId, token),
        listSessionFeedback(sessionId, token),
      ])
      messages.value = history.messages
      feedbackByMessageId.value = Object.fromEntries(
        feedback.map((item) => [item.message_id, item]),
      )

      const index = sessions.value.findIndex((item) => item.id === sessionId)
      if (index >= 0) {
        sessions.value[index] = history.session
      }
    } finally {
      loadingMessages.value = false
    }
  }

  async function ensureSession(): Promise<number> {
    if (activeSessionId.value !== null) {
      return activeSessionId.value
    }
    return (await createSession()).id
  }

  async function sendQuestion(rawQuestion: string): Promise<void> {
    const question = rawQuestion.trim()

    if (!question) {
      throw new ApiError(422, '请输入问题')
    }
    if (question.length > 500) {
      throw new ApiError(422, '单次提问不能超过 500 字')
    }
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，请稍候')
    }
    if (activeSession.value?.status === 'archived') {
      throw new ApiError(409, '该会话已归档，请先恢复后再继续提问')
    }

    const sessionId = await ensureSession()
    const token = requireToken()
    const tempUserId = newTemporaryId()

    const userMessage: ChatMessage = {
      id: tempUserId,
      session_id: sessionId,
      user_id: auth.user?.id ?? null,
      reply_to_message_id: null,
      role: 'user',
      content: question,
      intent: null,
      routed_knowledge_base_id: null,
      retrieval_status: null,
      is_fallback: false,
      question_char_count: question.length,
      prompt_token_estimate: null,
      completion_token_count: null,
      follow_up_suggestions: null,
      stream_completed_at: null,
      created_at: nowIso(),
      updated_at: nowIso(),
    }

    messages.value.push(userMessage)
    streaming.value = true
    streamText.value = ''
    streamSources.value = []
    streamError.value = ''
    currentIntent.value = null
    activeController = new AbortController()

    const completion: { value: ChatStreamDone | null } = { value: null }

    try {
      await streamChatAnswer({
        sessionId,
        question,
        token,
        signal: activeController.signal,
        onEvent(event) {
          if (event.event === 'meta') {
            const index = messages.value.findIndex(
              (item) => item.id === tempUserId,
            )
            if (index >= 0) {
              const currentMessage = messages.value[index]
              if (currentMessage) {
                messages.value[index] = {
                  ...currentMessage,
                  id: event.data.user_message_id,
                  intent: event.data.intent,
                }
              }
            }
            dailyQuestionCount.value = event.data.daily_question_count
            currentIntent.value = event.data.intent
            return
          }

          if (event.event === 'delta') {
            streamText.value += event.data.content
            return
          }

          if (event.event === 'replace') {
            streamText.value = event.data.content
            return
          }

          if (event.event === 'sources') {
            streamSources.value = event.data.items
            return
          }

          if (event.event === 'error') {
            streamError.value = event.data.message
            return
          }

          if (event.event === 'done') {
            completion.value = event.data
            streamText.value = event.data.content
          }
        },
      })

      const completed = completion.value
      if (!completed) {
        throw new ApiError(0, '流式回答结束，但没有收到 done 事件')
      }

      await openSessionAfterStream(sessionId)

      if (completed.source_count > 0) {
        sourcesByMessageId.value[completed.assistant_message_id] =
          streamSources.value.length > 0
            ? streamSources.value
            : await getMessageSources(
                completed.assistant_message_id,
                token,
              )
      }

      await loadSessions('active')
      activeSessionId.value = sessionId
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        streamError.value = '回答已停止'
      } else if (error instanceof ApiError) {
        streamError.value = error.detail
      } else {
        streamError.value = 'AI 回答失败，请稍后重试'
      }

      // 服务端可能已经保存了 user message；重新读取可避免本地状态与 MySQL 不一致。
      try {
        await openSessionAfterStream(sessionId)
        await loadSessions('active')
        activeSessionId.value = sessionId
      } catch {
        // 保留原始错误，不覆盖。
      }

      throw error
    } finally {
      streaming.value = false
      streamText.value = ''
      streamSources.value = []
      activeController = null
    }
  }

  async function openSessionAfterStream(sessionId: number): Promise<void> {
    const token = requireToken()
    const [history, feedback] = await Promise.all([
      getChatHistory(sessionId, token),
      listSessionFeedback(sessionId, token),
    ])
    activeSessionId.value = sessionId
    messages.value = history.messages
    feedbackByMessageId.value = Object.fromEntries(
      feedback.map((item) => [item.message_id, item]),
    )

    const index = sessions.value.findIndex((item) => item.id === sessionId)
    if (index >= 0) {
      sessions.value[index] = history.session
    }
  }

  function stopStreaming(): void {
    activeController?.abort()
  }

  async function loadSources(messageId: number): Promise<MessageSource[]> {
    const existing = sourcesByMessageId.value[messageId]
    if (existing) {
      return existing
    }

    const items = await getMessageSources(messageId, requireToken())
    sourcesByMessageId.value[messageId] = items
    return items
  }

  async function submitFeedback(
    messageId: number,
    rating: FeedbackRating,
    comment: string | null = null,
  ): Promise<void> {
    if (feedbackSubmittingMessageId.value !== null) {
      return
    }

    feedbackSubmittingMessageId.value = messageId
    try {
      const saved = await submitMessageFeedbackApi(
        messageId,
        rating,
        comment,
        requireToken(),
      )
      feedbackByMessageId.value = {
        ...feedbackByMessageId.value,
        [messageId]: saved,
      }
    } finally {
      feedbackSubmittingMessageId.value = null
    }
  }

  async function removeFeedback(messageId: number): Promise<void> {
    if (feedbackSubmittingMessageId.value !== null) {
      return
    }

    feedbackSubmittingMessageId.value = messageId
    try {
      await deleteMessageFeedbackApi(
        messageId,
        requireToken(),
      )
      const next = { ...feedbackByMessageId.value }
      delete next[messageId]
      feedbackByMessageId.value = next
    } finally {
      feedbackSubmittingMessageId.value = null
    }
  }

  async function renameSession(
    sessionId: number,
    title: string,
  ): Promise<void> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，暂时不能修改会话')
    }

    const target = sessions.value.find((item) => item.id === sessionId)
    if (target?.status === 'archived') {
      throw new ApiError(409, '已归档会话为只读状态，请先恢复后再重命名')
    }

    const normalizedTitle = title.trim()
    if (!normalizedTitle) {
      throw new ApiError(422, '会话标题不能为空')
    }

    const updated = await renameChatSession(
      sessionId,
      normalizedTitle,
      requireToken(),
    )

    const index = sessions.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) {
      sessions.value[index] = updated
    }
  }

  async function archiveSession(sessionId: number): Promise<void> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，暂时不能归档会话')
    }

    const target = sessions.value.find((item) => item.id === sessionId)
    if (target?.status === 'archived') {
      return
    }

    await archiveChatSession(sessionId, requireToken())
    sessions.value = sessions.value.filter((item) => item.id !== sessionId)

    if (activeSessionId.value === sessionId) {
      clearConversationState()
    }
  }

  async function restoreSession(sessionId: number): Promise<void> {
    if (streaming.value) {
      throw new ApiError(409, 'AI 正在回答，暂时不能恢复会话')
    }

    const restored = await restoreChatSession(
      sessionId,
      requireToken(),
    )

    await loadSessions('active')
    activeSessionId.value = restored.id
    await openSession(restored.id)
  }

  async function renameActiveSession(title: string): Promise<void> {
    if (activeSessionId.value === null) {
      return
    }
    await renameSession(activeSessionId.value, title)
  }

  async function archiveActiveSession(): Promise<void> {
    if (activeSessionId.value === null) {
      return
    }
    await archiveSession(activeSessionId.value)
  }

  async function restoreActiveSession(): Promise<void> {
    if (activeSessionId.value === null) {
      return
    }
    await restoreSession(activeSessionId.value)
  }

  function reset(): void {
    activeController?.abort()
    activeController = null
    sessions.value = []
    sessionMode.value = 'active'
    activeSessionId.value = null
    messages.value = []
    sourcesByMessageId.value = {}
    feedbackByMessageId.value = {}
    streaming.value = false
    streamText.value = ''
    streamSources.value = []
    streamError.value = ''
    dailyQuestionCount.value = null
    currentIntent.value = null
    feedbackSubmittingMessageId.value = null
  }

  return {
    sessions,
    sessionMode,
    activeSessionId,
    activeSession,
    messages,
    sourcesByMessageId,
    feedbackByMessageId,
    loadingSessions,
    loadingMessages,
    streaming,
    streamText,
    streamSources,
    streamError,
    dailyQuestionCount,
    currentIntent,
    feedbackSubmittingMessageId,
    loadSessions,
    showRecentSessions,
    showArchivedSessions,
    createSession,
    openSession,
    sendQuestion,
    stopStreaming,
    loadSources,
    submitFeedback,
    removeFeedback,
    renameSession,
    archiveSession,
    restoreSession,
    renameActiveSession,
    archiveActiveSession,
    restoreActiveSession,
    reset,
  }
})
