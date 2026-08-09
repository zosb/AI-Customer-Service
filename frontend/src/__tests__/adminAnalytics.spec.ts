import { describe, expect, it } from 'vitest'

import { buildLinePath, formatPercent } from '@/utils/adminAnalytics'


describe('admin analytics utils', () => {
  it('formats satisfaction percent', () => {
    expect(formatPercent(66.67)).toBe('66.7%')
  })

  it('builds an svg line path', () => {
    const path = buildLinePath(
      [
        { date: '2026-08-05', question_count: 1 },
        { date: '2026-08-06', question_count: 3 },
        { date: '2026-08-07', question_count: 2 },
      ],
      300,
      120,
      10,
    )
    expect(path.startsWith('M ')).toBe(true)
    expect(path.split(' L ')).toHaveLength(3)
  })

  it('returns empty path without points', () => {
    expect(buildLinePath([], 300, 120)).toBe('')
  })
})
