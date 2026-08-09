import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SessionSidebar from '@/components/chat/SessionSidebar.vue'
import type { ChatSession, ChatSessionStatus } from '@/types/chat'

const activeSessions: ChatSession[] = [
  {
    id: 11,
    user_id: 7,
    title: '退款到账时间',
    status: 'active',
    selected_knowledge_base_id: null,
    last_message_at: '2026-08-08T05:00:00Z',
    created_at: '2026-08-08T04:00:00Z',
    updated_at: '2026-08-08T05:00:00Z',
  },
  {
    id: 12,
    user_id: 7,
    title: '物流状态查询',
    status: 'active',
    selected_knowledge_base_id: null,
    last_message_at: null,
    created_at: '2026-08-08T04:10:00Z',
    updated_at: '2026-08-08T04:10:00Z',
  },
]

const archivedSessions: ChatSession[] = [
  {
    ...activeSessions[0]!,
    id: 21,
    title: '历史退款咨询',
    status: 'archived',
    updated_at: '2026-08-08T06:00:00Z',
  },
]

function mountSidebar(
  mode: ChatSessionStatus = 'active',
  sessions: ChatSession[] = activeSessions,
) {
  return mount(SessionSidebar, {
    props: {
      sessions,
      mode,
      activeSessionId: sessions[0]?.id ?? null,
      loading: false,
      disabled: false,
    },
  })
}

describe('SessionSidebar lifecycle actions', () => {
  it('emits select for the requested session', async () => {
    const wrapper = mountSidebar()
    const sessionButtons = wrapper.findAll('.session-select')

    await sessionButtons[1]?.trigger('click')

    expect(wrapper.emitted('select')).toEqual([[12]])
  })

  it('opens active row menu and emits rename with session id', async () => {
    const wrapper = mountSidebar()
    const menuButtons = wrapper.findAll('.session-menu-button')

    await menuButtons[0]?.trigger('click')
    expect(wrapper.text()).toContain('重命名')

    const renameButton = wrapper
      .findAll('.session-menu button')
      .find((item) => item.text() === '重命名')

    await renameButton?.trigger('click')
    expect(wrapper.emitted('rename')).toEqual([[11]])
  })

  it('emits archive for an active session', async () => {
    const wrapper = mountSidebar()
    const menuButtons = wrapper.findAll('.session-menu-button')

    await menuButtons[1]?.trigger('click')
    const archiveButton = wrapper
      .findAll('.session-menu button')
      .find((item) => item.text() === '归档')

    await archiveButton?.trigger('click')
    expect(wrapper.emitted('archive')).toEqual([[12]])
  })

  it('switches from recent sessions to archived sessions', async () => {
    const wrapper = mountSidebar()

    expect(wrapper.text()).toContain('最近会话')
    expect(wrapper.text()).toContain('查看归档会话')

    await wrapper.find('.session-mode-button').trigger('click')

    expect(wrapper.emitted('changeMode')).toEqual([['archived']])
  })

  it('archived mode exposes restore but not rename or archive', async () => {
    const wrapper = mountSidebar('archived', archivedSessions)

    expect(wrapper.text()).toContain('已归档会话')
    expect(wrapper.text()).toContain('返回最近会话')

    await wrapper.find('.session-menu-button').trigger('click')

    expect(wrapper.text()).toContain('恢复会话')
    expect(wrapper.text()).not.toContain('重命名')

    const restoreButton = wrapper
      .findAll('.session-menu button')
      .find((item) => item.text() === '恢复会话')

    await restoreButton?.trigger('click')
    expect(wrapper.emitted('restore')).toEqual([[21]])
  })

  it('does not open lifecycle menu while streaming is disabled', async () => {
    const wrapper = mount(SessionSidebar, {
      props: {
        sessions: activeSessions,
        mode: 'active',
        activeSessionId: 11,
        loading: false,
        disabled: true,
      },
    })

    const menuButton = wrapper.find('.session-menu-button')
    expect(menuButton.attributes('disabled')).toBeDefined()
    await menuButton.trigger('click')
    expect(wrapper.find('.session-menu').exists()).toBe(false)
  })
})
