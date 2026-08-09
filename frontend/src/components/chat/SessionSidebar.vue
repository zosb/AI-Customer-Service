<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import type { ChatSession, ChatSessionStatus } from '@/types/chat'
import { relativeApiTime } from '@/utils/datetime'

const props = defineProps<{
  sessions: ChatSession[]
  mode: ChatSessionStatus
  activeSessionId: number | null
  loading: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  create: []
  select: [sessionId: number]
  rename: [sessionId: number]
  archive: [sessionId: number]
  restore: [sessionId: number]
  changeMode: [mode: ChatSessionStatus]
}>()

const openMenuSessionId = ref<number | null>(null)

function relativeTime(session: ChatSession): string {
  const value =
    props.mode === 'archived'
      ? session.updated_at
      : session.last_message_at ?? session.created_at
  return relativeApiTime(value)
}

function toggleMenu(sessionId: number): void {
  if (props.disabled) {
    return
  }
  openMenuSessionId.value =
    openMenuSessionId.value === sessionId ? null : sessionId
}

function requestRename(sessionId: number): void {
  openMenuSessionId.value = null
  emit('rename', sessionId)
}

function requestArchive(sessionId: number): void {
  openMenuSessionId.value = null
  emit('archive', sessionId)
}

function requestRestore(sessionId: number): void {
  openMenuSessionId.value = null
  emit('restore', sessionId)
}

function switchMode(mode: ChatSessionStatus): void {
  openMenuSessionId.value = null
  if (mode !== props.mode) {
    emit('changeMode', mode)
  }
}

function closeMenu(): void {
  openMenuSessionId.value = null
}

function onDocumentClick(): void {
  closeMenu()
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <aside class="session-sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-logo">AI</div>
      <div>
        <p>AI CUSTOMER SERVICE</p>
        <strong>智能客服</strong>
      </div>
    </div>

    <button
      class="new-session-button"
      type="button"
      :disabled="disabled"
      @click="emit('create')"
    >
      <span>＋</span>
      新建对话
    </button>

    <div class="session-heading">
      <span>{{ mode === 'active' ? '最近会话' : '已归档会话' }}</span>
      <button
        class="session-mode-button"
        type="button"
        :disabled="disabled || loading"
        @click="switchMode(mode === 'active' ? 'archived' : 'active')"
      >
        {{ mode === 'active' ? '查看归档会话 →' : '← 返回最近会话' }}
      </button>
    </div>

    <div v-if="loading" class="session-loading">加载中...</div>

    <nav v-else class="session-list" aria-label="会话列表">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-row"
        :class="{
          active: session.id === activeSessionId,
          archived: mode === 'archived',
        }"
      >
        <button
          class="session-select"
          type="button"
          :disabled="disabled && session.id !== activeSessionId"
          @click="emit('select', session.id)"
        >
          <span class="session-title">{{ session.title }}</span>
          <span class="session-time">
            {{ mode === 'archived' ? '归档于 ' : '' }}{{ relativeTime(session) }}
          </span>
        </button>

        <div class="session-actions" @click.stop>
          <button
            class="session-menu-button"
            type="button"
            :disabled="disabled"
            :aria-expanded="openMenuSessionId === session.id"
            :aria-label="`管理会话：${session.title}`"
            title="管理会话"
            @click="toggleMenu(session.id)"
          >
            ···
          </button>

          <div
            v-if="openMenuSessionId === session.id"
            class="session-menu"
            role="menu"
          >
            <template v-if="mode === 'active'">
              <button
                type="button"
                role="menuitem"
                @click="requestRename(session.id)"
              >
                重命名
              </button>
              <button
                class="danger"
                type="button"
                role="menuitem"
                @click="requestArchive(session.id)"
              >
                归档
              </button>
            </template>

            <button
              v-else
              class="restore"
              type="button"
              role="menuitem"
              @click="requestRestore(session.id)"
            >
              恢复会话
            </button>
          </div>
        </div>
      </div>

      <div v-if="sessions.length === 0" class="empty-session">
        <template v-if="mode === 'active'">
          还没有历史会话
        </template>
        <template v-else>
          <strong>暂无已归档会话</strong>
          <span>归档后的历史对话会显示在这里。</span>
        </template>
      </div>
    </nav>

    <div class="sidebar-footer">
      <span class="online-dot"></span>
      本地 AI 服务
    </div>
  </aside>
</template>

<style scoped>
.session-sidebar {
  display: flex;
  min-height: 100vh;
  flex-direction: column;
  padding: 22px 16px;
  border-right: 1px solid #e4e9f1;
  background: rgb(248 250 253 / 96%);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 2px 8px 22px;
}

.sidebar-logo {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 12px;
  background: #182238;
  color: #fff;
  font-size: 13px;
  font-weight: 900;
}

.sidebar-brand p {
  margin: 0 0 2px;
  color: #778198;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .13em;
}

.sidebar-brand strong {
  color: #172033;
  font-size: 16px;
}

.new-session-button {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-radius: 12px;
  background: #3159d8;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}

.new-session-button:hover:not(:disabled) {
  background: #294dc0;
}

.new-session-button:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.session-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 25px 4px 10px 8px;
  color: #858ea1;
  font-size: 11px;
  font-weight: 800;
}

.session-heading > span {
  min-width: 0;
  white-space: nowrap;
}

.session-mode-button {
  flex: 0 0 auto;
  min-height: 26px;
  padding: 0 8px;
  border: 1px solid #dbe3f7;
  border-radius: 8px;
  background: #f7f9ff;
  color: #3159d8;
  font-size: 10px;
  font-weight: 800;
  white-space: nowrap;
  cursor: pointer;
}

.session-mode-button:hover:not(:disabled) {
  border-color: #bdcaf2;
  background: #edf2ff;
}

.session-mode-button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.session-loading {
  padding: 18px 10px;
  color: #9aa2b4;
  font-size: 12px;
  text-align: center;
}

.session-list {
  display: grid;
  gap: 6px;
}

.session-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 11px;
  background: transparent;
  transition: background .14s ease, border-color .14s ease;
}

.session-row:hover {
  background: #f0f3f9;
}

.session-row.active {
  border-color: #d7e0fb;
  background: #edf2ff;
}

.session-row.archived:not(.active) {
  background: #fbfcfe;
}

.session-select {
  display: grid;
  min-width: 0;
  gap: 4px;
  padding: 11px 4px 11px 12px;
  border: 0;
  background: transparent;
  color: #303a50;
  text-align: left;
  cursor: pointer;
}

.session-select:disabled {
  cursor: not-allowed;
}

.session-title {
  overflow: hidden;
  font-size: 13px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  color: #939bae;
  font-size: 10px;
}

.session-actions {
  position: relative;
  align-self: stretch;
  display: grid;
  place-items: center;
  padding-right: 5px;
}

.session-menu-button {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #7d879b;
  font-size: 16px;
  font-weight: 900;
  line-height: 1;
  opacity: 0;
  cursor: pointer;
}

.session-row:hover .session-menu-button,
.session-row.active .session-menu-button,
.session-menu-button[aria-expanded='true'] {
  opacity: 1;
}

.session-menu-button:hover:not(:disabled) {
  background: #fff;
  color: #26324a;
  box-shadow: 0 4px 12px rgb(31 45 72 / 10%);
}

.session-menu-button:disabled {
  cursor: not-allowed;
  opacity: .35;
}

.session-menu {
  position: absolute;
  z-index: 20;
  top: 36px;
  right: 5px;
  display: grid;
  min-width: 112px;
  padding: 5px;
  border: 1px solid #dde3ee;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 14px 32px rgb(29 43 70 / 16%);
}

.session-menu button {
  padding: 8px 10px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #303a50;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.session-menu button:hover {
  background: #f4f6fa;
}

.session-menu button.danger {
  color: #c54848;
}

.session-menu button.danger:hover {
  background: #fff1f1;
}

.session-menu button.restore {
  color: #3159d8;
  font-weight: 750;
}

.session-menu button.restore:hover {
  background: #edf2ff;
}

.empty-session {
  display: grid;
  gap: 5px;
  padding: 20px 10px;
  color: #9aa2b4;
  font-size: 12px;
  text-align: center;
}

.empty-session strong {
  color: #727c91;
  font-size: 12px;
}

.empty-session span {
  font-size: 10px;
  line-height: 1.6;
}

.sidebar-footer {
  display: flex;
  margin-top: auto;
  align-items: center;
  gap: 7px;
  padding: 14px 9px 2px;
  color: #828b9f;
  font-size: 11px;
}

.online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22b573;
}
</style>
