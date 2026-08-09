import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteMessageFeedback,
  listSessionFeedback,
  submitMessageFeedback,
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


describe('chat feedback api', () => {
  it('submits like/dislike with optional comment', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        id: 1,
        message_id: 8,
        user_id: 3,
        rating: -1,
        comment: '希望更具体',
        created_at: '2026-08-07T09:30:00',
        updated_at: '2026-08-07T09:30:00',
      }),
    )

    const result = await submitMessageFeedback(
      8,
      -1,
      '希望更具体',
      'jwt-token',
    )

    expect(result.rating).toBe(-1)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/chat/messages/8/feedback'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          rating: -1,
          comment: '希望更具体',
        }),
      }),
    )
  })

  it('loads all feedback for one session', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse([
        {
          id: 1,
          message_id: 8,
          user_id: 3,
          rating: 1,
          comment: null,
          created_at: '2026-08-07T09:30:00',
          updated_at: '2026-08-07T09:30:00',
        },
      ]),
    )

    const result = await listSessionFeedback(2, 'jwt-token')
    expect(result).toHaveLength(1)
    expect(result[0]?.message_id).toBe(8)
  })

  it('deletes feedback', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        message_id: 8,
        status: 'deleted',
      }),
    )

    const result = await deleteMessageFeedback(8, 'jwt-token')
    expect(result.status).toBe('deleted')
  })
})
