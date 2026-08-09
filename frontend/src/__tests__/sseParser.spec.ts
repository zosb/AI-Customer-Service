import { describe, expect, it } from 'vitest'

import { SseParser } from '@/utils/sse'

describe('SseParser', () => {
  it('parses complete SSE events', () => {
    const parser = new SseParser()
    const events = parser.push(
      'event: delta\ndata: {"content":"你"}\n\n' +
        'event: done\ndata: {"assistant_message_id":1}\n\n',
    )

    expect(events).toEqual([
      {
        event: 'delta',
        data: '{"content":"你"}',
      },
      {
        event: 'done',
        data: '{"assistant_message_id":1}',
      },
    ])
  })

  it('handles an event split across network chunks', () => {
    const parser = new SseParser()

    expect(parser.push('event: del')).toEqual([])
    expect(
      parser.push('ta\ndata: {"content":"三个'),
    ).toEqual([])

    expect(
      parser.push('工作日"}\n\n'),
    ).toEqual([
      {
        event: 'delta',
        data: '{"content":"三个工作日"}',
      },
    ])
  })

  it('supports multiple data lines', () => {
    const parser = new SseParser()
    const events = parser.push(
      'event: test\ndata: first\ndata: second\n\n',
    )

    expect(events[0]).toEqual({
      event: 'test',
      data: 'first\nsecond',
    })
  })
})
