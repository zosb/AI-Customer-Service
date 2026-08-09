import { describe, expect, it } from 'vitest'

import { knowledgeBaseLabel } from '@/utils/knowledgeRouting'

describe('knowledge routing UI helpers', () => {
  it('shows the knowledge base name when it is loaded', () => {
    expect(
      knowledgeBaseLabel(7, {
        7: '退款政策',
      }),
    ).toBe('退款政策')
  })

  it('falls back to the knowledge base id when name is unavailable', () => {
    expect(
      knowledgeBaseLabel(12, {}),
    ).toBe('#12')
  })

  it('does not display a blank knowledge base name', () => {
    expect(
      knowledgeBaseLabel(3, {
        3: '   ',
      }),
    ).toBe('#3')
  })
})
