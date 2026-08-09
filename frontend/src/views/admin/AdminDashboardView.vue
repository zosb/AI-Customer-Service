<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useAdminStore } from '@/stores/admin'
import { useAuthStore } from '@/stores/auth'
import { buildLinePath, formatPercent } from '@/utils/adminAnalytics'

const admin = useAdminStore()
const auth = useAuthStore()
const router = useRouter()
const errorMessage = ref('')
const sessionQuery = ref('')

const linePath = computed(() =>
  buildLinePath(admin.trend?.items ?? [], 720, 210, 22),
)
const maxQuestionCount = computed(() =>
  Math.max(
    ...(admin.trend?.items.map((item) => item.question_count) ?? [0]),
    1,
  ),
)
const canPrevious = computed(() => admin.sessionOffset > 0)
const canNext = computed(
  () => admin.sessionOffset + admin.sessionLimit < admin.sessionTotal,
)

onMounted(async () => {
  await runSafely(() => admin.initialize())
})

async function runSafely(action: () => Promise<void>): Promise<void> {
  errorMessage.value = ''
  try {
    await action()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.detail
      if (error.status === 401) {
        auth.logout()
        await router.replace('/login')
      }
      if (error.status === 403) {
        await router.replace('/')
      }
      return
    }
    errorMessage.value = '管理后台加载失败，请稍后重试'
  }
}

async function searchSessions(): Promise<void> {
  await runSafely(() => admin.loadSessionPage(0, sessionQuery.value))
}

async function previousPage(): Promise<void> {
  if (!canPrevious.value) return
  await runSafely(() =>
    admin.loadSessionPage(
      admin.sessionOffset - admin.sessionLimit,
      sessionQuery.value,
    ),
  )
}

async function nextPage(): Promise<void> {
  if (!canNext.value) return
  await runSafely(() =>
    admin.loadSessionPage(
      admin.sessionOffset + admin.sessionLimit,
      sessionQuery.value,
    ),
  )
}

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function compactText(value: string, max = 72): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length <= max
    ? normalized
    : `${normalized.slice(0, max)}…`
}
</script>

<template>
  <main class="admin-page">
    <header class="admin-header">
      <div>
        <p>AI CUSTOMER SERVICE / ADMIN</p>
        <h1>运营管理后台</h1>
        <span>全量会话、用户反馈与日均问答量</span>
      </div>
      <div class="header-actions">
        <button type="button" @click="router.push('/admin/agent')">Agent 规划</button>
        <button type="button" @click="router.push('/knowledge')">知识库</button>
        <button type="button" @click="router.push('/')">返回客服</button>
      </div>
    </header>

    <div v-if="errorMessage" class="alert">{{ errorMessage }}</div>

    <section v-if="admin.overview" class="metric-grid">
      <article class="metric-card">
        <span>今日问答</span>
        <strong>{{ admin.overview.today_questions }}</strong>
        <small>每日上限统计口径</small>
      </article>
      <article class="metric-card">
        <span>累计用户</span>
        <strong>{{ admin.overview.total_users }}</strong>
        <small>活跃 {{ admin.overview.active_users }}</small>
      </article>
      <article class="metric-card">
        <span>累计会话</span>
        <strong>{{ admin.overview.total_sessions }}</strong>
        <small>进行中 {{ admin.overview.active_sessions }}</small>
      </article>
      <article class="metric-card">
        <span>满意率</span>
        <strong>{{ formatPercent(admin.overview.satisfaction_rate) }}</strong>
        <small>{{ admin.overview.feedback_total }} 条反馈</small>
      </article>
      <article class="metric-card">
        <span>知识库 / 文档</span>
        <strong>{{ admin.overview.total_knowledge_bases }} / {{ admin.overview.total_documents }}</strong>
        <small>当前未删除数据</small>
      </article>
      <article class="metric-card">
        <span>Token 估算</span>
        <strong>{{ admin.overview.prompt_token_estimate + admin.overview.completion_token_count }}</strong>
        <small>Prompt + Completion</small>
      </article>
    </section>

    <section class="analytics-grid">
      <article class="panel trend-panel">
        <div class="panel-title">
          <div>
            <p>DAILY QUESTIONS</p>
            <h2>日均问答量折线图</h2>
          </div>
          <div v-if="admin.trend" class="trend-summary">
            <strong>{{ admin.trend.average_per_day }}</strong>
            <span>近 {{ admin.trend.days }} 天日均</span>
          </div>
        </div>

        <div v-if="admin.trend" class="chart-wrap">
          <svg viewBox="0 0 720 210" role="img" aria-label="日均问答量折线图">
            <line v-for="index in 4" :key="index" x1="22" x2="698" :y1="index * 42" :y2="index * 42" class="grid-line" />
            <path v-if="linePath" :d="linePath" class="trend-line" />
            <template v-for="(item, index) in admin.trend.items" :key="item.date">
              <circle
                :cx="admin.trend.items.length === 1 ? 360 : 22 + (676 * index) / (admin.trend.items.length - 1)"
                :cy="188 - (item.question_count / maxQuestionCount) * 166"
                r="4"
                class="trend-point"
              />
            </template>
          </svg>
          <div class="chart-labels">
            <span v-for="item in admin.trend.items" :key="item.date">{{ item.date.slice(5) }}</span>
          </div>
        </div>
        <div v-else class="empty">正在读取趋势…</div>
      </article>

      <article class="panel feedback-panel">
        <div class="panel-title">
          <div>
            <p>FEEDBACK</p>
            <h2>用户反馈统计</h2>
          </div>
        </div>
        <div v-if="admin.feedbackSummary" class="feedback-summary">
          <div><strong>{{ admin.feedbackSummary.positive }}</strong><span>👍 有帮助</span></div>
          <div><strong>{{ admin.feedbackSummary.negative }}</strong><span>👎 没帮助</span></div>
          <div><strong>{{ formatPercent(admin.feedbackSummary.satisfaction_rate) }}</strong><span>满意率</span></div>
        </div>
        <div v-if="admin.feedbackSummary" class="intent-list">
          <div v-for="item in admin.feedbackSummary.by_intent.slice(0, 6)" :key="item.intent" class="intent-row">
            <span>{{ item.intent }}</span>
            <div class="intent-track"><i :style="{ width: `${item.satisfaction_rate}%` }" /></div>
            <strong>{{ formatPercent(item.satisfaction_rate) }}</strong>
          </div>
          <div v-if="admin.feedbackSummary.by_intent.length === 0" class="empty">暂时没有用户反馈</div>
        </div>
      </article>
    </section>

    <section class="panel sessions-panel">
      <div class="panel-title session-title-row">
        <div>
          <p>ALL SESSIONS</p>
          <h2>全量会话记录</h2>
        </div>
        <form class="session-search" @submit.prevent="searchSessions">
          <input v-model="sessionQuery" maxlength="100" placeholder="搜索会话标题 / 用户" />
          <button type="submit">搜索</button>
        </form>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>会话</th><th>用户</th><th>消息</th><th>状态</th><th>最后活动</th><th /></tr>
          </thead>
          <tbody>
            <tr v-for="item in admin.sessions" :key="item.id">
              <td><strong>{{ item.title }}</strong><small>#{{ item.id }}</small></td>
              <td>{{ item.user_label }}</td>
              <td>{{ item.message_count }}</td>
              <td><span class="status-chip" :class="item.status">{{ item.status === 'active' ? '进行中' : '已归档' }}</span></td>
              <td>{{ formatDateTime(item.last_message_at || item.created_at) }}</td>
              <td><button class="text-button" type="button" @click="runSafely(() => admin.openSession(item.id))">查看</button></td>
            </tr>
            <tr v-if="admin.sessions.length === 0"><td colspan="6" class="empty-cell">没有符合条件的会话</td></tr>
          </tbody>
        </table>
      </div>
      <footer class="pager">
        <span>共 {{ admin.sessionTotal }} 个会话</span>
        <div>
          <button type="button" :disabled="!canPrevious" @click="previousPage">上一页</button>
          <button type="button" :disabled="!canNext" @click="nextPage">下一页</button>
        </div>
      </footer>
    </section>

    <section class="panel latest-feedback">
      <div class="panel-title"><div><p>LATEST FEEDBACK</p><h2>最近反馈</h2></div></div>
      <div class="feedback-list">
        <article v-for="item in admin.feedback" :key="item.id">
          <span class="rating" :class="item.rating === 1 ? 'positive' : 'negative'">{{ item.rating === 1 ? '👍' : '👎' }}</span>
          <div>
            <strong>{{ item.user_label }} · {{ item.intent || 'general' }}</strong>
            <p>{{ item.comment || compactText(item.assistant_content) }}</p>
            <small>{{ item.session_title }} · {{ formatDateTime(item.created_at) }}</small>
          </div>
        </article>
        <div v-if="admin.feedback.length === 0" class="empty">暂无反馈</div>
      </div>
    </section>

    <div v-if="admin.selectedSession" class="modal-backdrop" @click.self="admin.closeSession">
      <section class="session-modal">
        <header>
          <div><p>SESSION #{{ admin.selectedSession.session.id }}</p><h2>{{ admin.selectedSession.session.title }}</h2><span>{{ admin.selectedSession.session.user_label }}</span></div>
          <button type="button" @click="admin.closeSession">关闭</button>
        </header>
        <div class="message-list">
          <article v-for="message in admin.selectedSession.messages" :key="message.id" :class="['admin-message', message.role]">
            <div class="message-meta">
              <strong>{{ message.role === 'user' ? '用户' : message.role === 'assistant' ? 'AI' : '系统' }}</strong>
              <span v-if="message.intent">{{ message.intent }}</span>
              <span v-if="message.routed_knowledge_base_id">KB {{ message.routed_knowledge_base_id }}</span>
              <span v-if="message.feedback_rating">{{ message.feedback_rating === 1 ? '👍' : '👎' }}</span>
            </div>
            <p>{{ message.content }}</p>
            <small>{{ formatDateTime(message.created_at) }}</small>
          </article>
          <div v-if="admin.selectedSession.messages.length === 0" class="empty">当前会话没有消息</div>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.admin-page { min-height: 100vh; padding: 28px 34px 54px; background: #f5f7fb; color: #111d35; }
.admin-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; max-width: 1440px; margin: 0 auto 22px; }
.admin-header p,.panel-title p { margin: 0 0 5px; color: #7c8aa7; font-size: 10px; font-weight: 900; letter-spacing: .14em; }
.admin-header h1 { margin: 0; font-size: 30px; letter-spacing: -.04em; }
.admin-header span { display: block; margin-top: 6px; color: #7b879f; font-size: 13px; }
.header-actions { display: flex; gap: 8px; }
.header-actions button,.pager button,.session-search button,.session-modal header button { padding: 9px 13px; border: 1px solid #dfe5ef; border-radius: 10px; background: #fff; color: #1c2941; font-weight: 700; cursor: pointer; }
.alert { max-width: 1440px; margin: 0 auto 18px; padding: 12px 14px; border: 1px solid #ffd1d1; border-radius: 12px; background: #fff4f4; color: #a73939; }
.metric-grid { display: grid; max-width: 1440px; margin: 0 auto 18px; grid-template-columns: repeat(6,minmax(0,1fr)); gap: 12px; }
.metric-card,.panel { border: 1px solid #e2e7f0; border-radius: 18px; background: #fff; box-shadow: 0 10px 30px rgb(24 39 75 / 4%); }
.metric-card { padding: 18px; }
.metric-card span { color: #7a869c; font-size: 11px; font-weight: 800; }
.metric-card strong { display: block; margin: 8px 0 4px; font-size: 26px; letter-spacing: -.04em; }
.metric-card small { color: #9aa4b6; }
.analytics-grid { display: grid; max-width: 1440px; margin: 0 auto 18px; grid-template-columns: minmax(0,1.7fr) minmax(320px,.8fr); gap: 16px; }
.panel { padding: 20px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.panel-title h2 { margin: 0; font-size: 18px; }
.trend-summary { text-align: right; }
.trend-summary strong { display: block; font-size: 22px; }
.trend-summary span { color: #8c97aa; font-size: 11px; }
.chart-wrap { overflow: hidden; }
.chart-wrap svg { width: 100%; min-height: 220px; }
.grid-line { stroke: #edf0f5; stroke-width: 1; }
.trend-line { fill: none; stroke: #315de7; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; }
.trend-point { fill: #fff; stroke: #315de7; stroke-width: 3; }
.chart-labels { display: flex; justify-content: space-between; gap: 3px; color: #9aa4b6; font-size: 9px; }
.feedback-summary { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; margin-bottom: 18px; }
.feedback-summary div { padding: 12px; border-radius: 12px; background: #f7f9fd; }
.feedback-summary strong { display: block; font-size: 20px; }
.feedback-summary span { color: #8792a6; font-size: 10px; }
.intent-list { display: grid; gap: 10px; }
.intent-row { display: grid; grid-template-columns: 80px minmax(0,1fr) 48px; align-items: center; gap: 8px; font-size: 11px; }
.intent-track { height: 7px; overflow: hidden; border-radius: 999px; background: #edf0f6; }
.intent-track i { display: block; height: 100%; border-radius: inherit; background: #315de7; }
.sessions-panel,.latest-feedback { max-width: 1440px; margin: 0 auto 18px; }
.session-title-row { align-items: flex-end; }
.session-search { display: flex; gap: 7px; }
.session-search input { width: 260px; padding: 9px 11px; border: 1px solid #dfe5ef; border-radius: 10px; outline: none; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th { padding: 10px; border-bottom: 1px solid #e8ecf3; color: #8792a6; font-size: 10px; text-align: left; }
td { padding: 13px 10px; border-bottom: 1px solid #f0f2f6; font-size: 12px; }
td strong { display: block; }
td small { color: #a0a8b7; }
.status-chip { padding: 4px 8px; border-radius: 999px; background: #eef9f2; color: #27874c; font-size: 10px; font-weight: 800; }
.status-chip.archived { background: #f1f2f5; color: #7d8490; }
.text-button { border: 0; background: none; color: #315de7; font-weight: 800; cursor: pointer; }
.empty-cell,.empty { padding: 24px; color: #9aa4b6; text-align: center; }
.pager { display: flex; align-items: center; justify-content: space-between; padding-top: 14px; color: #8994a8; font-size: 11px; }
.pager div { display: flex; gap: 7px; }
.pager button:disabled { opacity: .4; cursor: default; }
.feedback-list { display: grid; gap: 9px; }
.feedback-list article { display: grid; grid-template-columns: 34px minmax(0,1fr); gap: 10px; padding: 12px; border-radius: 12px; background: #f8f9fc; }
.feedback-list strong { font-size: 12px; }
.feedback-list p { margin: 4px 0; color: #4e5b72; font-size: 12px; }
.feedback-list small { color: #9aa4b6; }
.rating { display: grid; width: 32px; height: 32px; place-items: center; border-radius: 10px; background: #eef8f1; }
.rating.negative { background: #fff2f0; }
.modal-backdrop { position: fixed; z-index: 50; inset: 0; display: grid; place-items: center; padding: 28px; background: rgb(10 20 40 / 42%); }
.session-modal { display: grid; width: min(820px,100%); max-height: 82vh; grid-template-rows: auto minmax(0,1fr); overflow: hidden; border-radius: 20px; background: #fff; box-shadow: 0 24px 80px rgb(0 0 0 / 20%); }
.session-modal header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px; border-bottom: 1px solid #e8ecf3; }
.session-modal header p { margin: 0; color: #8b96aa; font-size: 9px; font-weight: 900; letter-spacing: .12em; }
.session-modal header h2 { margin: 4px 0; font-size: 18px; }
.session-modal header span { color: #7c879b; font-size: 11px; }
.message-list { display: grid; gap: 10px; overflow: auto; padding: 18px; }
.admin-message { padding: 13px 14px; border: 1px solid #e7ebf2; border-radius: 14px; background: #fff; }
.admin-message.user { margin-left: 12%; background: #f2f6ff; }
.admin-message.assistant { margin-right: 12%; }
.message-meta { display: flex; gap: 7px; align-items: center; color: #7d899f; font-size: 9px; }
.admin-message p { margin: 8px 0; color: #2f3a4e; font-size: 12px; line-height: 1.7; white-space: pre-wrap; }
.admin-message small { color: #a1a8b6; }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(3,1fr); } .analytics-grid { grid-template-columns: 1fr; } }
@media (max-width: 720px) { .admin-page { padding: 18px 12px 40px; } .admin-header { flex-direction: column; } .metric-grid { grid-template-columns: repeat(2,1fr); } .session-title-row { align-items: stretch; flex-direction: column; } .session-search input { width: 100%; } .chart-labels span:nth-child(even) { display: none; } }
</style>
