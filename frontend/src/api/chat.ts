import {
  API_BASE_URL,
  ApiError,
  requestJson,
  resolveApiErrorDetail,
} from '@/api/http'
import type {
  ChatMessageHistoryResponse,
  ChatSession,
  ChatSessionStatus,
  ChatSessionListResponse,
  ChatStreamEvent,
  FeedbackRating,
  MessageFeedback,
  MessageFeedbackDeleteResponse,
  MessageSource,
} from '@/types/chat'
import { SseParser } from '@/utils/sse'

interface StreamChatOptions {
  sessionId: number
  question: string
  token: string
  signal?: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}

export async function listChatSessions(
  token: string,
  status: ChatSessionStatus = 'active',
): Promise<ChatSessionListResponse> {
  const query = new URLSearchParams({
    status,
    limit: '100',
    offset: '0',
  })

  return requestJson<ChatSessionListResponse>(
    `/api/v1/chat/sessions?${query.toString()}`,
    {},
    token,
  )
}

export async function createChatSession(
  token: string,
): Promise<ChatSession> {
  return requestJson<ChatSession>(
    '/api/v1/chat/sessions',
    {
      method: 'POST',
      body: JSON.stringify({
        title: '新会话',
        selected_knowledge_base_id: null,
      }),
    },
    token,
  )
}

export async function getChatHistory(
  sessionId: number,
  token: string,
): Promise<ChatMessageHistoryResponse> {
  return requestJson<ChatMessageHistoryResponse>(
    `/api/v1/chat/sessions/${sessionId}/messages`,
    {},
    token,
  )
}

export async function getMessageSources(
  messageId: number,
  token: string,
): Promise<MessageSource[]> {
  return requestJson<MessageSource[]>(
    `/api/v1/chat/messages/${messageId}/sources`,
    {},
    token,
  )
}

export async function listSessionFeedback(
  sessionId: number,
  token: string,
): Promise<MessageFeedback[]> {
  return requestJson<MessageFeedback[]>(
    `/api/v1/chat/sessions/${sessionId}/feedback`,
    {},
    token,
  )
}

export async function submitMessageFeedback(
  messageId: number,
  rating: FeedbackRating,
  comment: string | null,
  token: string,
): Promise<MessageFeedback> {
  return requestJson<MessageFeedback>(
    `/api/v1/chat/messages/${messageId}/feedback`,
    {
      method: 'PUT',
      body: JSON.stringify({ rating, comment }),
    },
    token,
  )
}

export async function deleteMessageFeedback(
  messageId: number,
  token: string,
): Promise<MessageFeedbackDeleteResponse> {
  return requestJson<MessageFeedbackDeleteResponse>(
    `/api/v1/chat/messages/${messageId}/feedback`,
    { method: 'DELETE' },
    token,
  )
}

export async function renameChatSession(
  sessionId: number,
  title: string,
  token: string,
): Promise<ChatSession> {
  return requestJson<ChatSession>(
    `/api/v1/chat/sessions/${sessionId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    },
    token,
  )
}

export async function archiveChatSession(
  sessionId: number,
  token: string,
): Promise<void> {
  await requestJson(
    `/api/v1/chat/sessions/${sessionId}`,
    { method: 'DELETE' },
    token,
  )
}

export async function restoreChatSession(
  sessionId: number,
  token: string,
): Promise<ChatSession> {
  return requestJson<ChatSession>(
    `/api/v1/chat/sessions/${sessionId}/restore`,
    { method: 'POST' },
    token,
  )
}

export async function streamChatAnswer({
  sessionId,
  question,
  token,
  signal,
  onEvent,
}: StreamChatOptions): Promise<void> {
  let response: Response

  try {
    response = await fetch(
      `${API_BASE_URL}/api/v1/chat/sessions/${sessionId}/messages`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ question }),
        signal,
      },
    )
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ApiError(
      0,
      '无法连接后端服务，请检查 FastAPI 服务或本机网络连接',
    )
  }

  if (!response.ok) {
    throw await responseToApiError(response)
  }

  if (!response.body) {
    throw new ApiError(0, '浏览器未收到流式响应体')
  }

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('text/event-stream')) {
    throw new ApiError(
      response.status,
      `服务端未返回 SSE 流：${contentType || 'unknown'}`,
    )
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  const parser = new SseParser()

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }

      const chunk = decoder.decode(value, { stream: true })
      for (const raw of parser.push(chunk)) {
        emitTypedEvent(raw.event, raw.data, onEvent)
      }
    }

    const tail = decoder.decode()
    for (const raw of parser.push(tail)) {
      emitTypedEvent(raw.event, raw.data, onEvent)
    }
    for (const raw of parser.finish()) {
      emitTypedEvent(raw.event, raw.data, onEvent)
    }
  } finally {
    reader.releaseLock()
  }
}

function emitTypedEvent(
  event: string,
  rawData: string,
  onEvent: (event: ChatStreamEvent) => void,
): void {
  let payload: unknown

  try {
    payload = JSON.parse(rawData)
  } catch {
    throw new ApiError(0, `SSE ${event} 事件包含无效 JSON`)
  }

  if (
    event !== 'meta' &&
    event !== 'delta' &&
    event !== 'replace' &&
    event !== 'sources' &&
    event !== 'done' &&
    event !== 'error'
  ) {
    return
  }

  onEvent({
    event,
    data: payload,
  } as ChatStreamEvent)
}

async function responseToApiError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get('content-type') ?? ''
  let payload: unknown = null

  if (contentType.includes('application/json')) {
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
  }

  return new ApiError(
    response.status,
    resolveApiErrorDetail(response.status, payload),
  )
}
