<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useAgentStore } from '@/stores/agent'
import { useAuthStore } from '@/stores/auth'
import {
  formatPlanningDuration,
  groupSafeBatches,
  indexTasks,
  totalTokenCount,
} from '@/utils/agentPlan'

const agent = useAgentStore()
const auth = useAuthStore()
const router = useRouter()

const requirement = ref('')
const systemContext = ref('')
const errorMessage = ref('')

const tasksById = computed(() => indexTasks(agent.result))
const safeBatchGroups = computed(() => groupSafeBatches(agent.result))
const totalTokens = computed(() => totalTokenCount(agent.result))

const sampleRequirement =
  '用户下单成功后自动发送短信通知；如果短信发送失败，需要记录失败原因，但不能影响订单创建接口返回成功。'

const sampleSystemContext = `系统当前包含以下服务：

1. frontend-web
- 负责用户下单页面。
- 本需求无需修改前端页面。

2. order-service
- POST /orders 创建订单。
- 当前订单创建逻辑完成数据库事务后直接返回 HTTP 200。
- 可发布 OrderCreated 领域事件。
- OrderCreated 包含 event_id、order_id、user_id、created_at。

3. user-service
- 已存在 GET /internal/users/{user_id}/contact。
- 可以查询用户手机号。
- 本需求只复用现有接口，不需要修改 user-service。

4. notification-service
- 负责短信通知。
- 需要消费 OrderCreated。
- 消费后调用 user-service 查询手机号。
- 调用现有 SMSProvider.send 发送短信。
- notification_delivery 表可记录 event_id、status、failure_reason。
- 必须通过 event_id 做幂等，短信失败不能反向影响 order-service。`

function loadExample(): void {
  requirement.value = sampleRequirement
  systemContext.value = sampleSystemContext
  errorMessage.value = ''
}

async function generatePlan(): Promise<void> {
  const normalizedRequirement = requirement.value.trim()
  const normalizedContext = systemContext.value.trim()

  if (!normalizedRequirement || !normalizedContext) {
    errorMessage.value = '请完整填写用户需求和系统技术 / 接口文档'
    return
  }

  errorMessage.value = ''

  try {
    await agent.generate({
      requirement: normalizedRequirement,
      system_context: normalizedContext,
    })
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.detail
      if (error.status === 401) {
        auth.logout()
        await router.replace('/login')
      } else if (error.status === 403) {
        await router.replace('/')
      }
      return
    }

    errorMessage.value = 'Agent 规划失败，请稍后重试'
  }
}

function taskTitle(taskId: string): string {
  return tasksById.value[taskId]?.title ?? taskId
}

function taskService(taskId: string): string {
  return tasksById.value[taskId]?.service ?? 'unknown'
}
</script>

<template>
  <main class="agent-page">
    <header class="agent-header">
      <div>
        <p>AI CUSTOMER SERVICE / AGENT</p>
        <h1>多微服务任务规划</h1>
        <span>需求拆解 → Dependency DAG → 资源冲突 → 安全执行批次</span>
      </div>

      <div class="header-actions">
        <button type="button" @click="router.push('/admin')">
          运营后台
        </button>
        <button type="button" @click="router.push('/')">
          返回客服
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="alert">
      {{ errorMessage }}
    </div>

    <section class="planner-input panel">
      <div class="panel-title">
        <div>
          <p>PLAN REQUEST</p>
          <h2>输入研发需求与系统上下文</h2>
        </div>
        <button class="secondary-button" type="button" @click="loadExample">
          加载示例
        </button>
      </div>

      <div class="input-grid">
        <label>
          <span>用户需求</span>
          <textarea
            v-model="requirement"
            maxlength="4000"
            rows="9"
            placeholder="例如：用户下单成功后自动发送短信通知……"
          />
          <small>{{ requirement.length }}/4000</small>
        </label>

        <label>
          <span>系统技术 / 接口文档</span>
          <textarea
            v-model="systemContext"
            maxlength="24000"
            rows="9"
            placeholder="粘贴微服务职责、现有 API、数据库表、事件定义等技术上下文……"
          />
          <small>{{ systemContext.length }}/24000</small>
        </label>
      </div>

      <div class="submit-row">
        <p>
          Planner 只生成研发执行计划，不直接修改代码或执行生产操作。
        </p>
        <button
          class="primary-button"
          type="button"
          :disabled="agent.loading"
          @click="generatePlan"
        >
          {{ agent.loading ? 'AI 正在规划…' : '生成执行计划' }}
        </button>
      </div>
    </section>

    <template v-if="agent.result">
      <section class="metric-grid">
        <article class="metric-card">
          <span>模型</span>
          <strong class="metric-model">{{ agent.result.model }}</strong>
          <small>本地 Ollama Planner</small>
        </article>
        <article class="metric-card">
          <span>受影响服务</span>
          <strong>{{ agent.result.plan.services.length }}</strong>
          <small>只统计需要修改的服务</small>
        </article>
        <article class="metric-card">
          <span>原子任务</span>
          <strong>{{ agent.result.plan.tasks.length }}</strong>
          <small>{{ agent.result.dependency.edges.length }} 条依赖边</small>
        </article>
        <article class="metric-card">
          <span>执行阶段</span>
          <strong>{{ agent.result.dependency.stages.length }}</strong>
          <small>拓扑分层</small>
        </article>
        <article class="metric-card">
          <span>安全并行度</span>
          <strong>{{ agent.result.parallel_safety.max_safe_parallelism }}</strong>
          <small>资源冲突检查后</small>
        </article>
        <article class="metric-card">
          <span>规划耗时</span>
          <strong class="metric-time">
            {{ formatPlanningDuration(agent.result.planning_ms) }}
          </strong>
          <small>{{ totalTokens }} Tokens</small>
        </article>
      </section>

      <section class="panel summary-panel">
        <div class="panel-title compact">
          <div>
            <p>REQUIREMENT SUMMARY</p>
            <h2>Agent 需求理解</h2>
          </div>
        </div>
        <p class="summary-text">{{ agent.result.plan.requirement_summary }}</p>
      </section>

      <section class="panel">
        <div class="panel-title">
          <div>
            <p>IMPACTED SERVICES</p>
            <h2>受影响微服务</h2>
          </div>
          <span class="count-chip">
            {{ agent.result.plan.services.length }} services
          </span>
        </div>

        <div class="service-grid">
          <article
            v-for="service in agent.result.plan.services"
            :key="service.name"
            class="service-card"
          >
            <div class="service-icon">SVC</div>
            <div>
              <h3>{{ service.name }}</h3>
              <p>{{ service.reason }}</p>
              <div class="tag-row">
                <span
                  v-for="scope in service.change_scope"
                  :key="scope"
                  class="soft-tag"
                >
                  {{ scope }}
                </span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <div>
            <p>DEPENDENCY DAG</p>
            <h2>任务依赖与拓扑执行阶段</h2>
          </div>
          <div class="dag-meta">
            <span>Roots: {{ agent.result.dependency.root_tasks.join(', ') }}</span>
            <span>Terminals: {{ agent.result.dependency.terminal_tasks.join(', ') }}</span>
          </div>
        </div>

        <div class="stage-flow">
          <template
            v-for="(stage, stageIndex) in agent.result.dependency.stages"
            :key="stage.index"
          >
            <article class="stage-card">
              <header>
                <div>
                  <small>STAGE {{ stage.index }}</small>
                  <strong>
                    {{
                      stage.parallel_candidate
                        ? '依赖图并行候选'
                        : '串行 / 单任务'
                    }}
                  </strong>
                </div>
                <span>{{ stage.task_ids.length }} tasks</span>
              </header>

              <div class="stage-tasks">
                <div
                  v-for="taskId in stage.task_ids"
                  :key="taskId"
                  class="task-card"
                >
                  <div class="task-heading">
                    <span>{{ taskId }}</span>
                    <em>{{ taskService(taskId) }}</em>
                  </div>
                  <h3>{{ taskTitle(taskId) }}</h3>
                  <p>{{ tasksById[taskId]?.description }}</p>
                  <div class="task-deps">
                    depends_on:
                    {{
                      tasksById[taskId]?.depends_on.length
                        ? tasksById[taskId]?.depends_on.join(', ')
                        : 'none'
                    }}
                  </div>
                </div>
              </div>
            </article>
            <div
              v-if="stageIndex < agent.result.dependency.stages.length - 1"
              class="stage-arrow"
              aria-hidden="true"
            >
              ↓
            </div>
          </template>
        </div>

        <div class="critical-path">
          <strong>关键路径</strong>
          <template
            v-for="(taskId, index) in agent.result.dependency.critical_path"
            :key="taskId"
          >
            <span>{{ taskId }}</span>
            <i v-if="index < agent.result.dependency.critical_path.length - 1">→</i>
          </template>
        </div>
      </section>

      <section class="parallel-grid">
        <article class="panel">
          <div class="panel-title">
            <div>
              <p>SAFE EXECUTION</p>
              <h2>安全执行批次</h2>
            </div>
            <span class="success-chip">
              max {{ agent.result.parallel_safety.max_safe_parallelism }}
            </span>
          </div>

          <div class="batch-list">
            <div
              v-for="group in safeBatchGroups"
              :key="group.stageIndex"
              class="batch-stage"
            >
              <strong>Stage {{ group.stageIndex }}</strong>
              <div class="batch-row">
                <article
                  v-for="batch in group.batches"
                  :key="`${batch.stage_index}-${batch.batch_index}`"
                  class="batch-card"
                  :class="{ parallel: batch.parallel_safe }"
                >
                  <small>Batch {{ batch.batch_index }}</small>
                  <b>{{ batch.task_ids.join(' + ') }}</b>
                  <span>
                    {{
                      batch.parallel_safe
                        ? '安全并行'
                        : '顺序执行'
                    }}
                  </span>
                </article>
              </div>
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-title">
            <div>
              <p>RESOURCE SAFETY</p>
              <h2>资源冲突</h2>
            </div>
            <span
              class="count-chip"
              :class="{ danger: agent.result.parallel_safety.conflicts.length }"
            >
              {{ agent.result.parallel_safety.conflicts.length }} conflicts
            </span>
          </div>

          <div
            v-if="agent.result.parallel_safety.conflicts.length"
            class="conflict-list"
          >
            <article
              v-for="conflict in agent.result.parallel_safety.conflicts"
              :key="`${conflict.stage_index}-${conflict.task_a}-${conflict.task_b}`"
            >
              <strong>
                Stage {{ conflict.stage_index }} ·
                {{ conflict.task_a }} ↔ {{ conflict.task_b }}
              </strong>
              <p>{{ conflict.reason }}</p>
              <div class="tag-row">
                <span
                  v-for="resource in conflict.shared_resources"
                  :key="resource"
                  class="danger-tag"
                >
                  {{ resource }}
                </span>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">
            当前计划没有检测到同 Stage 资源冲突。
          </div>
        </article>
      </section>

      <section class="panel">
        <div class="panel-title">
          <div>
            <p>RESOURCE PROFILE</p>
            <h2>任务资源画像</h2>
          </div>
        </div>

        <div class="resource-table-wrap">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>微服务</th>
                <th>资源</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="profile in agent.result.parallel_safety.task_resources"
                :key="profile.task_id"
              >
                <td>
                  <strong>{{ profile.task_id }}</strong>
                  <small>{{ taskTitle(profile.task_id) }}</small>
                </td>
                <td>{{ profile.service }}</td>
                <td>
                  <div class="tag-row">
                    <span
                      v-for="resource in profile.resources"
                      :key="resource"
                      class="resource-tag"
                    >
                      {{ resource }}
                    </span>
                    <span v-if="!profile.resources.length" class="muted">
                      未提取到显式资源
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="notes-grid">
        <article class="panel">
          <div class="panel-title compact">
            <div>
              <p>ASSUMPTIONS</p>
              <h2>规划假设</h2>
            </div>
          </div>
          <ul v-if="agent.result.plan.assumptions.length">
            <li
              v-for="item in agent.result.plan.assumptions"
              :key="item"
            >
              {{ item }}
            </li>
          </ul>
          <div v-else class="empty-state">无额外假设</div>
        </article>

        <article class="panel">
          <div class="panel-title compact">
            <div>
              <p>RISKS</p>
              <h2>风险与缓解</h2>
            </div>
          </div>
          <ul v-if="agent.result.plan.risks.length" class="risk-list">
            <li
              v-for="item in agent.result.plan.risks"
              :key="item"
            >
              {{ item }}
            </li>
          </ul>
          <div v-else class="empty-state">未发现额外风险</div>
        </article>
      </section>
    </template>

    <section v-else class="empty-hero">
      <div class="agent-mark">AI</div>
      <h2>等待生成 Agent 执行计划</h2>
      <p>
        输入需求和系统技术文档后，将展示受影响微服务、原子任务、
        DAG、关键路径、资源冲突和安全执行批次。
      </p>
    </section>
  </main>
</template>

<style scoped>
.agent-page {
  min-height: 100vh;
  padding: 26px 30px 60px;
  background: #f4f7fc;
  color: #111d35;
}
.agent-header {
  display: flex;
  max-width: 1440px;
  margin: 0 auto 22px;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}
.agent-header p,
.panel-title p {
  margin: 0 0 5px;
  color: #7c8aa7;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .14em;
}
.agent-header h1 {
  margin: 0;
  font-size: 30px;
  letter-spacing: -.04em;
}
.agent-header span {
  display: block;
  margin-top: 6px;
  color: #7b879f;
  font-size: 13px;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.header-actions button,
.secondary-button {
  padding: 9px 13px;
  border: 1px solid #dfe5ef;
  border-radius: 10px;
  background: #fff;
  color: #1c2941;
  font-weight: 700;
  cursor: pointer;
}
.alert {
  max-width: 1440px;
  margin: 0 auto 18px;
  padding: 12px 14px;
  border: 1px solid #ffd1d1;
  border-radius: 12px;
  background: #fff4f4;
  color: #a73939;
}
.panel,
.metric-card {
  border: 1px solid #e2e7f0;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 10px 30px rgb(24 39 75 / 4%);
}
.panel {
  max-width: 1440px;
  margin: 0 auto 18px;
  padding: 20px;
}
.panel-title {
  display: flex;
  margin-bottom: 16px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.panel-title.compact {
  margin-bottom: 10px;
}
.panel-title h2 {
  margin: 0;
  font-size: 18px;
}
.input-grid {
  display: grid;
  grid-template-columns: minmax(0, .78fr) minmax(0, 1.22fr);
  gap: 14px;
}
.input-grid label {
  display: grid;
  gap: 7px;
}
.input-grid label > span {
  color: #33405a;
  font-size: 12px;
  font-weight: 800;
}
.input-grid textarea {
  min-height: 190px;
  padding: 13px 14px;
  resize: vertical;
  border: 1px solid #dfe5ef;
  border-radius: 13px;
  outline: none;
  background: #fbfcff;
  color: #28344b;
  font: inherit;
  font-size: 12px;
  line-height: 1.7;
}
.input-grid textarea:focus {
  border-color: #7796f3;
  box-shadow: 0 0 0 3px rgb(49 93 231 / 8%);
}
.input-grid small {
  color: #a0a9b9;
  text-align: right;
}
.submit-row {
  display: flex;
  margin-top: 14px;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.submit-row p {
  margin: 0;
  color: #8a95a8;
  font-size: 11px;
}
.primary-button {
  min-width: 156px;
  padding: 11px 18px;
  border: 0;
  border-radius: 11px;
  background: #315de7;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}
.primary-button:disabled {
  opacity: .55;
  cursor: wait;
}
.metric-grid {
  display: grid;
  max-width: 1440px;
  margin: 0 auto 18px;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}
.metric-card {
  padding: 18px;
}
.metric-card span {
  color: #7a869c;
  font-size: 11px;
  font-weight: 800;
}
.metric-card strong {
  display: block;
  margin: 8px 0 4px;
  font-size: 26px;
  letter-spacing: -.04em;
}
.metric-card .metric-model,
.metric-card .metric-time {
  font-size: 18px;
}
.metric-card small {
  color: #9aa4b6;
}
.summary-text {
  margin: 0;
  color: #33405a;
  font-size: 14px;
  line-height: 1.8;
}
.count-chip,
.success-chip {
  padding: 5px 9px;
  border-radius: 999px;
  background: #f0f4ff;
  color: #315de7;
  font-size: 10px;
  font-weight: 900;
}
.success-chip {
  background: #ecf9f1;
  color: #23884b;
}
.count-chip.danger {
  background: #fff1ef;
  color: #c34a3d;
}
.service-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.service-card {
  display: grid;
  padding: 15px;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 12px;
  border: 1px solid #e5eaf3;
  border-radius: 14px;
}
.service-icon {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 12px;
  background: #17233b;
  color: #fff;
  font-size: 9px;
  font-weight: 900;
}
.service-card h3 {
  margin: 0 0 6px;
  font-size: 14px;
}
.service-card p {
  margin: 0 0 9px;
  color: #677389;
  font-size: 11px;
  line-height: 1.6;
}
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.soft-tag,
.resource-tag,
.danger-tag {
  padding: 4px 7px;
  border-radius: 7px;
  background: #f1f4fa;
  color: #536177;
  font-size: 9px;
  font-weight: 700;
}
.resource-tag {
  background: #edf3ff;
  color: #3158c8;
}
.danger-tag {
  background: #fff0ed;
  color: #ba4739;
}
.dag-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
}
.dag-meta span {
  padding: 5px 8px;
  border-radius: 8px;
  background: #f5f7fb;
  color: #778398;
  font-size: 9px;
}
.stage-flow {
  display: grid;
  gap: 7px;
}
.stage-card {
  border: 1px solid #e5eaf2;
  border-radius: 15px;
  background: #fbfcff;
}
.stage-card > header {
  display: flex;
  padding: 12px 14px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #edf0f5;
}
.stage-card > header div {
  display: grid;
  gap: 2px;
}
.stage-card > header small {
  color: #315de7;
  font-size: 9px;
  font-weight: 900;
}
.stage-card > header strong {
  font-size: 12px;
}
.stage-card > header span {
  color: #8b96aa;
  font-size: 10px;
}
.stage-tasks {
  display: grid;
  padding: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 9px;
}
.task-card {
  padding: 12px;
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  background: #fff;
}
.task-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.task-heading span {
  display: grid;
  width: 31px;
  height: 25px;
  place-items: center;
  border-radius: 7px;
  background: #17233b;
  color: #fff;
  font-size: 9px;
  font-weight: 900;
}
.task-heading em {
  overflow: hidden;
  color: #315de7;
  font-size: 9px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-card h3 {
  margin: 10px 0 5px;
  font-size: 12px;
}
.task-card p {
  margin: 0;
  color: #68758b;
  font-size: 10px;
  line-height: 1.65;
}
.task-deps {
  margin-top: 9px;
  color: #9aa4b5;
  font-size: 9px;
}
.stage-arrow {
  color: #7c91d6;
  font-size: 20px;
  font-weight: 900;
  text-align: center;
}
.critical-path {
  display: flex;
  margin-top: 13px;
  padding: 11px 12px;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  border-radius: 11px;
  background: #f4f7fd;
  font-size: 10px;
}
.critical-path strong {
  margin-right: 6px;
}
.critical-path span {
  padding: 4px 7px;
  border-radius: 7px;
  background: #fff;
  color: #315de7;
  font-weight: 900;
}
.critical-path i {
  color: #98a3b4;
  font-style: normal;
}
.parallel-grid,
.notes-grid {
  display: grid;
  max-width: 1440px;
  margin: 0 auto;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.parallel-grid > .panel,
.notes-grid > .panel {
  width: auto;
  margin: 0 0 18px;
}
.batch-list {
  display: grid;
  gap: 12px;
}
.batch-stage {
  display: grid;
  gap: 7px;
}
.batch-stage > strong {
  color: #657188;
  font-size: 10px;
}
.batch-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.batch-card {
  display: grid;
  min-width: 135px;
  padding: 10px 11px;
  gap: 3px;
  border: 1px solid #e6eaf2;
  border-radius: 11px;
  background: #fafbfe;
}
.batch-card.parallel {
  border-color: #ccebd7;
  background: #f1fbf5;
}
.batch-card small {
  color: #8c97a8;
  font-size: 8px;
}
.batch-card b {
  font-size: 11px;
}
.batch-card span {
  color: #7b8798;
  font-size: 9px;
}
.batch-card.parallel span {
  color: #25844b;
}
.conflict-list {
  display: grid;
  gap: 8px;
}
.conflict-list article {
  padding: 11px;
  border: 1px solid #f2d7d2;
  border-radius: 11px;
  background: #fff8f7;
}
.conflict-list strong {
  font-size: 10px;
}
.conflict-list p {
  margin: 5px 0 8px;
  color: #795c59;
  font-size: 10px;
  line-height: 1.55;
}
.resource-table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th {
  padding: 9px;
  border-bottom: 1px solid #e9edf4;
  color: #8c97aa;
  font-size: 9px;
  text-align: left;
}
td {
  padding: 11px 9px;
  border-bottom: 1px solid #f0f2f6;
  color: #39465b;
  font-size: 10px;
}
td strong,
td small {
  display: block;
}
td small {
  margin-top: 3px;
  color: #9aa4b6;
}
.muted,
.empty-state {
  color: #9aa4b6;
  font-size: 10px;
}
.empty-state {
  padding: 28px 10px;
  text-align: center;
}
.notes-grid ul {
  display: grid;
  margin: 0;
  padding-left: 18px;
  gap: 7px;
  color: #526078;
  font-size: 11px;
  line-height: 1.6;
}
.risk-list li::marker {
  color: #d17b31;
}
.empty-hero {
  display: grid;
  max-width: 680px;
  min-height: 280px;
  margin: 50px auto 0;
  place-items: center;
  align-content: center;
  padding: 40px;
  text-align: center;
}
.agent-mark {
  display: grid;
  width: 54px;
  height: 54px;
  margin-bottom: 12px;
  place-items: center;
  border-radius: 16px;
  background: #17233b;
  color: #fff;
  font-weight: 900;
}
.empty-hero h2 {
  margin: 0;
  font-size: 22px;
}
.empty-hero p {
  max-width: 540px;
  margin: 9px 0 0;
  color: #8490a4;
  font-size: 12px;
  line-height: 1.7;
}
@media (max-width: 1100px) {
  .metric-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .input-grid,
  .parallel-grid,
  .notes-grid {
    grid-template-columns: 1fr;
  }
  .service-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 720px) {
  .agent-page {
    padding: 18px 12px 40px;
  }
  .agent-header {
    flex-direction: column;
  }
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .submit-row {
    align-items: stretch;
    flex-direction: column;
  }
  .primary-button {
    width: 100%;
  }
}
</style>
