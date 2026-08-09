<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import SessionSidebar from '@/components/chat/SessionSidebar.vue'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'
import type { ChatSessionStatus, FeedbackRating } from '@/types/chat'

const authStore = useAuthStore()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()
const router = useRouter()

const pageError = ref('')
const suggestedQuestion = ref('')

const accountLabel = computed(
  () =>
    authStore.user?.display_name ||
    authStore.user?.email ||
    authStore.user?.phone ||
    '用户',
)

const knowledgeBaseNamesById = computed<
  Record<number, string>
>(() => {
  const result: Record<number, string> = {}

  for (const item of knowledgeStore.bases) {
    result[item.id] = item.name
  }

  return result
})

const archivedEmptyMessage = computed(() => {
  if (chatStore.sessionMode !== 'archived') {
    return ''
  }

  if (chatStore.sessions.length === 0) {
    return '暂无已归档会话'
  }

  if (!chatStore.activeSession) {
    return '请选择左侧归档会话查看历史记录'
  }

  return '此归档会话暂无消息记录'
})

onMounted(async () => {
  await runSafely(async () => {
    await Promise.all([
      chatStore.loadSessions(),
      knowledgeStore.loadBases(),
    ])
  })
})

async function runSafely(action: () => Promise<void>): Promise<void> {
  pageError.value = ''

  try {
    await action()
  } catch (error) {
    if (error instanceof ApiError) {
      pageError.value = error.detail
      if (error.status === 401) {
        await logout()
      }
      return
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }

    pageError.value = '操作失败，请稍后重试'
  }
}

async function createSession(): Promise<void> {
  await runSafely(async () => {
    await chatStore.createSession()
  })
}

async function changeSessionMode(mode: ChatSessionStatus): Promise<void> {
  await runSafely(async () => {
    if (mode === 'archived') {
      await chatStore.showArchivedSessions()
      return
    }

    await chatStore.showRecentSessions()
  })
}

async function openSession(sessionId: number): Promise<void> {
  if (sessionId === chatStore.activeSessionId) {
    return
  }

  await runSafely(async () => {
    await chatStore.openSession(sessionId)
  })
}

async function sendQuestion(question: string): Promise<void> {
  await runSafely(async () => {
    await chatStore.sendQuestion(question)
  })
}

async function loadSources(messageId: number): Promise<void> {
  await runSafely(async () => {
    await chatStore.loadSources(messageId)
  })
}

async function submitFeedback(
  messageId: number,
  rating: FeedbackRating,
  comment: string | null,
): Promise<void> {
  await runSafely(async () => {
    await chatStore.submitFeedback(
      messageId,
      rating,
      comment,
    )
  })
}

async function removeFeedback(messageId: number): Promise<void> {
  await runSafely(async () => {
    await chatStore.removeFeedback(messageId)
  })
}

async function renameSession(sessionId?: number): Promise<void> {
  const targetId = sessionId ?? chatStore.activeSessionId
  if (targetId === null) {
    return
  }

  const session = chatStore.sessions.find((item) => item.id === targetId)
  if (!session) {
    return
  }

  const value = window.prompt('修改会话标题', session.title)
  if (value === null) {
    return
  }

  await runSafely(async () => {
    await chatStore.renameSession(targetId, value)
  })
}

async function archiveSession(sessionId?: number): Promise<void> {
  const targetId = sessionId ?? chatStore.activeSessionId
  if (targetId === null) {
    return
  }

  const session = chatStore.sessions.find((item) => item.id === targetId)
  if (!session) {
    return
  }

  if (
    !window.confirm(
      `归档会话“${session.title}”？\n\n归档后不会继续显示在最近会话中，但历史记录仍会保留。`,
    )
  ) {
    return
  }

  await runSafely(async () => {
    await chatStore.archiveSession(targetId)
  })
}

async function restoreSession(sessionId?: number): Promise<void> {
  const targetId = sessionId ?? chatStore.activeSessionId
  if (targetId === null) {
    return
  }

  await runSafely(async () => {
    await chatStore.restoreSession(targetId)
  })
}

function useSuggestion(value: string): void {
  if (chatStore.sessionMode === 'archived') {
    return
  }
  suggestedQuestion.value = value
}

async function logout(): Promise<void> {
  chatStore.reset()
  knowledgeStore.reset()
  authStore.logout()
  await router.replace('/login')
}
</script>

<template>
  <main class="chat-workspace">
    <SessionSidebar
      :sessions="chatStore.sessions"
      :mode="chatStore.sessionMode"
      :active-session-id="chatStore.activeSessionId"
      :loading="chatStore.loadingSessions"
      :disabled="chatStore.streaming"
      @create="createSession"
      @select="openSession"
      @rename="renameSession"
      @archive="archiveSession"
      @restore="restoreSession"
      @change-mode="changeSessionMode"
    />

    <section class="chat-main">
      <header class="chat-topbar">
        <div class="topbar-title">
          <p>
            {{
              chatStore.activeSession
                ? chatStore.activeSession.status === 'archived'
                  ? '已归档会话 · 只读'
                  : '当前会话'
                : chatStore.sessionMode === 'archived'
                  ? '已归档会话'
                  : 'AI CUSTOMER SERVICE'
            }}
          </p>
          <h1>
            {{
              chatStore.activeSession?.title ??
              'AI 智能客服系统'
            }}
          </h1>
        </div>

        <div class="topbar-actions">
          <span
            v-if="chatStore.currentIntent"
            class="intent-status"
          >
            意图：{{ chatStore.currentIntent }}
          </span>

          <button
            v-if="chatStore.activeSession?.status === 'active'"
            class="icon-button"
            type="button"
            :disabled="chatStore.streaming"
            title="修改会话标题"
            @click="renameSession()"
          >
            编辑
          </button>

          <button
            v-if="chatStore.activeSession?.status === 'active'"
            class="icon-button danger"
            type="button"
            :disabled="chatStore.streaming"
            title="归档会话"
            @click="archiveSession()"
          >
            归档
          </button>

          <button
            v-if="chatStore.activeSession?.status === 'archived'"
            class="icon-button restore-button"
            type="button"
            :disabled="chatStore.streaming"
            title="恢复会话后可继续提问"
            @click="restoreSession()"
          >
            恢复会话
          </button>

          <button
            class="icon-button"
            type="button"
            title="管理企业知识库"
            @click="router.push('/knowledge')"
          >
            知识库
          </button>

          <button
            v-if="authStore.user?.role === 'admin'"
            class="icon-button"
            type="button"
            title="进入运营管理后台"
            @click="router.push('/admin')"
          >
            管理后台
          </button>

          <button
            v-if="authStore.user?.role === 'admin'"
            class="icon-button"
            type="button"
            title="进入 AI Agent 多微服务任务规划"
            @click="router.push('/admin/agent')"
          >
            Agent
          </button>

          <div class="user-chip">
            <span>{{ accountLabel.slice(0, 1).toUpperCase() }}</span>
            <strong>{{ accountLabel }}</strong>
          </div>

          <button
            class="logout-button"
            type="button"
            @click="logout"
          >
            退出
          </button>
        </div>
      </header>

      <div v-if="pageError || chatStore.streamError" class="page-alert">
        {{ pageError || chatStore.streamError }}
      </div>

      <ChatMessageList
        :messages="chatStore.messages"
        :streaming="chatStore.streaming"
        :stream-text="chatStore.streamText"
        :stream-sources="chatStore.streamSources"
        :sources-by-message-id="chatStore.sourcesByMessageId"
        :feedback-by-message-id="chatStore.feedbackByMessageId"
        :feedback-submitting-message-id="chatStore.feedbackSubmittingMessageId"
        :knowledge-base-names-by-id="knowledgeBaseNamesById"
        :loading="chatStore.loadingMessages"
        :read-only="chatStore.sessionMode === 'archived'"
        :read-only-empty-message="archivedEmptyMessage"
        @load-sources="loadSources"
        @suggestion="useSuggestion"
        @feedback="submitFeedback"
        @remove-feedback="removeFeedback"
      />

      <div
        v-if="chatStore.sessionMode === 'archived'"
        class="archived-readonly-shell"
      >
        <div class="archived-readonly-card">
          <div>
            <strong>
              {{ chatStore.activeSession ? '此会话已归档' : '已归档会话' }}
            </strong>
            <span>
              {{
                chatStore.activeSession
                  ? '历史消息与知识来源仍然保留；恢复后可继续提问。'
                  : '请选择左侧归档记录查看完整历史；归档记录不会被删除。'
              }}
            </span>
          </div>
          <button
            v-if="chatStore.activeSession"
            type="button"
            :disabled="chatStore.loadingMessages"
            @click="restoreSession()"
          >
            恢复会话
          </button>
        </div>
      </div>

      <ChatComposer
        v-else
        :disabled="chatStore.loadingMessages"
        :streaming="chatStore.streaming"
        :daily-question-count="chatStore.dailyQuestionCount"
        :suggested-question="suggestedQuestion"
        @send="sendQuestion"
        @stop="chatStore.stopStreaming"
        @consumed-suggestion="suggestedQuestion = ''"
      />
    </section>
  </main>
</template>

<style scoped>
.chat-workspace {
  display: grid;
  min-height: 100vh;
  grid-template-columns: 248px minmax(0, 1fr);
  background: #f5f7fb;
}

.chat-main {
  position: relative;
  display: grid;
  min-width: 0;
  height: 100vh;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
}

.chat-topbar {
  display: flex;
  min-height: 76px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 28px;
  border-bottom: 1px solid #e5e9f0;
  background: rgb(255 255 255 / 85%);
  backdrop-filter: blur(16px);
}

.topbar-title p {
  margin: 0 0 3px;
  color: #8a93a6;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .12em;
}

.topbar-title h1 {
  margin: 0;
  font-size: 18px;
  letter-spacing: -.025em;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.intent-status {
  padding: 7px 9px;
  border-radius: 9px;
  background: #edf2ff;
  color: #4963c1;
  font-size: 10px;
  font-weight: 800;
}

.icon-button,
.logout-button {
  min-height: 34px;
  padding: 0 11px;
  border: 1px solid #dfe4ec;
  border-radius: 9px;
  background: #fff;
  color: #59647a;
  font-size: 11px;
  font-weight: 750;
  cursor: pointer;
}

.icon-button.danger:hover {
  border-color: #f0c4c4;
  color: #b44343;
}

.icon-button.restore-button {
  border-color: #cbd7ff;
  background: #f4f7ff;
  color: #3159d8;
}

.archived-readonly-shell {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  padding: 18px clamp(18px, 5vw, 64px) 18px;
  background: linear-gradient(to top, #f5f7fb 76%, rgb(245 247 251 / 0%));
}

.archived-readonly-card {
  display: flex;
  max-width: 920px;
  min-height: 72px;
  margin: 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 16px;
  border: 1px solid #d7deea;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 14px 42px rgb(34 47 79 / 9%);
}

.archived-readonly-card div {
  display: grid;
  gap: 4px;
}

.archived-readonly-card strong {
  color: #2e3b56;
  font-size: 13px;
}

.archived-readonly-card span {
  color: #7d879b;
  font-size: 11px;
}

.archived-readonly-card button {
  flex: 0 0 auto;
  min-height: 36px;
  padding: 0 14px;
  border: 0;
  border-radius: 10px;
  background: #3159d8;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}

.archived-readonly-card button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.user-chip {
  display: flex;
  min-height: 36px;
  align-items: center;
  gap: 7px;
  padding: 0 9px 0 6px;
  border: 1px solid #e0e5ed;
  border-radius: 11px;
  background: #fff;
}

.user-chip span {
  display: grid;
  width: 25px;
  height: 25px;
  place-items: center;
  border-radius: 8px;
  background: #172033;
  color: #fff;
  font-size: 10px;
  font-weight: 900;
}

.user-chip strong {
  max-width: 130px;
  overflow: hidden;
  color: #465168;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-alert {
  position: absolute;
  z-index: 10;
  top: 86px;
  right: 24px;
  max-width: 390px;
  padding: 10px 13px;
  border: 1px solid #f0c6c6;
  border-radius: 10px;
  background: #fff2f2;
  color: #a33b3b;
  font-size: 11px;
  box-shadow: 0 10px 25px rgb(80 30 30 / 8%);
}

@media (max-width: 900px) {
  .chat-workspace {
    grid-template-columns: 190px minmax(0, 1fr);
  }

  .chat-topbar {
    padding-inline: 16px;
  }

  .user-chip strong,
  .intent-status {
    display: none;
  }
}

@media (max-width: 680px) {
  .chat-workspace {
    display: block;
  }

  :deep(.session-sidebar) {
    display: none;
  }

  .chat-main {
    height: 100vh;
  }
}
</style>
