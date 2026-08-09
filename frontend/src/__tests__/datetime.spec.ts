import { describe, expect, it } from 'vitest'

import {
  parseApiDate,
  relativeApiTime,
} from '@/utils/datetime'

describe('API datetime helpers', () => {
  it('treats timezone-less backend datetime as UTC', () => {
    expect(
      parseApiDate('2026-08-07T09:15:00').toISOString(),
    ).toBe('2026-08-07T09:15:00.000Z')
  })

  it('keeps datetime that already contains timezone offset', () => {
    expect(
      parseApiDate(
        '2026-08-07T17:15:00+08:00',
      ).toISOString(),
    ).toBe('2026-08-07T09:15:00.000Z')
  })

  it('shows a just-created UTC record as just now in UTC+8 browser scenario', () => {
    const now = Date.parse('2026-08-07T09:15:30Z')

    expect(
      relativeApiTime(
        '2026-08-07T09:15:00',
        now,
      ),
    ).toBe('刚刚')
  })

  it('still calculates normal relative minutes', () => {
    const now = Date.parse('2026-08-07T09:25:00Z')

    expect(
      relativeApiTime(
        '2026-08-07T09:15:00',
        now,
      ),
    ).toBe('10 分钟前')
  })
})
