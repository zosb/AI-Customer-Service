import { afterEach, describe, expect, it, vi } from 'vitest'

import { streamChatAnswer } from '@/api/chat'

afterEach(() => {
  vi.restoreAllMocks()
})

function makeSseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
    },
  })
}

describe('streamChatAnswer', () => {
  it('emits meta delta sources and done events', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      makeSseResponse([
        'event: meta\ndata: {"session_id":1,"user_message_id":2,"intent":"refund","daily_question_count":1,"retrieval_status":"matched"}\n\n',
        'event: delta\ndata: {"content":"三个"}\n\n',
        'event: delta\ndata: {"content":"工作日"}\n\n',
        'event: sources\ndata: {"items":[]}\n\n',
        'event: done\ndata: {"assistant_message_id":3,"content":"三个工作日","is_fallback":false,"retrieval_status":"matched","follow_up_suggestions":[],"source_count":0}\n\n',
      ]),
    )

    const names: string[] = []

    await streamChatAnswer({
      sessionId: 1,
      question: '退款多久？',
      token: 'jwt-token',
      onEvent(event) {
        names.push(event.event)
      },
    })

    expect(names).toEqual([
      'meta',
      'delta',
      'delta',
      'sources',
      'done',
    ])

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/chat/sessions/1/messages'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer jwt-token',
          Accept: 'text/event-stream',
        }),
      }),
    )
  })

  it('parses SSE events even when JSON is split across chunks', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      makeSseResponse([
        'event: delta\ndata: {"content":"退',
        '款"}\n\nevent: done\ndata: {"assistant_message_id":3,"content":"退款","is_fallback":false,"retrieval_status":"matched","follow_up_suggestions":[],"source_count":0}\n\n',
      ]),
    )

    const contents: string[] = []

    await streamChatAnswer({
      sessionId: 1,
      question: '退款？',
      token: 'token',
      onEvent(event) {
        if (event.event === 'delta') {
          contents.push(event.data.content)
        }
      },
    })

    expect(contents).toEqual(['退款'])
  })
})
