import { afterEach, describe, expect, it, vi } from 'vitest'

import { streamChatAnswer } from '@/api/chat'
import { requestJson } from '@/api/http'
import type { ChatStreamEvent } from '@/types/chat'

afterEach(() => {
  vi.restoreAllMocks()
})

function streamOptions() {
  return {
    sessionId: 21,
    question: '退款进度怎么查询？',
    token: 'jwt-token',
    onEvent: vi.fn<(event: ChatStreamEvent) => void>(),
  }
}

describe('frontend API error classification', () => {
  it('reports an actual fetch failure as a backend/network connection problem', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(
      new TypeError('Failed to fetch'),
    )

    await expect(requestJson('/api/v1/health')).rejects.toMatchObject({
      status: 0,
      detail: '无法连接后端服务，请检查 FastAPI 服务或本机网络连接',
    })
  })

  it('maps a plain HTTP 500 response to a server-processing error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )

    await expect(requestJson('/api/v1/example')).rejects.toMatchObject({
      status: 500,
      detail: '服务端处理异常，请稍后重试',
    })
  })

  it('does not mislabel an SSE HTTP 500 response as FastAPI being offline', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )

    await expect(streamChatAnswer(streamOptions())).rejects.toMatchObject({
      status: 500,
      detail: '服务端处理异常，请稍后重试',
    })
  })

  it('preserves a backend detail message for an SSE validation failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: '单次提问长度不能超过 500 字' }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(streamChatAnswer(streamOptions())).rejects.toMatchObject({
      status: 422,
      detail: '单次提问长度不能超过 500 字',
    })
  })

  it('reports an SSE fetch failure as a connection problem only', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(
      new TypeError('Failed to fetch'),
    )

    await expect(streamChatAnswer(streamOptions())).rejects.toMatchObject({
      status: 0,
      detail: '无法连接后端服务，请检查 FastAPI 服务或本机网络连接',
    })
  })
})
