import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChatMessageList from '@/components/chat/ChatMessageList.vue'

function mountEmptyArchive(message: string) {
  return mount(ChatMessageList, {
    props: {
      messages: [],
      streaming: false,
      streamText: '',
      streamSources: [],
      sourcesByMessageId: {},
      feedbackByMessageId: {},
      feedbackSubmittingMessageId: null,
      knowledgeBaseNamesById: {},
      loading: false,
      readOnly: true,
      readOnlyEmptyMessage: message,
    },
  })
}

describe('ChatMessageList archived empty states', () => {
  it('distinguishes an unselected archive from a truly empty conversation', () => {
    const wrapper = mountEmptyArchive('请选择左侧归档会话查看历史记录')

    expect(wrapper.text()).toContain('请选择左侧归档会话查看历史记录')
    expect(wrapper.text()).toContain('选择一条归档记录后即可查看完整对话与知识来源')
    expect(wrapper.text()).not.toContain('此归档会话暂无消息记录')
  })

  it('shows a dedicated empty archive-center message when no archived sessions exist', () => {
    const wrapper = mountEmptyArchive('暂无已归档会话')

    expect(wrapper.text()).toContain('暂无已归档会话')
    expect(wrapper.text()).toContain('归档后的历史对话会显示在左侧归档列表中')
  })
})
