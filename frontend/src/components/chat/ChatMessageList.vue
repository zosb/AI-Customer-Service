<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import type {
  ChatMessage,
  FeedbackRating,
  MessageFeedback,
  MessageSource,
} from '@/types/chat'
import { knowledgeBaseLabel } from '@/utils/knowledgeRouting'

const props = defineProps<{
  messages: ChatMessage[]
  streaming: boolean
  streamText: string
  streamSources: MessageSource[]
  sourcesByMessageId: Record<number, MessageSource[]>
  feedbackByMessageId: Record<number, MessageFeedback>
  feedbackSubmittingMessageId: number | null
  knowledgeBaseNamesById: Record<number, string>
  loading: boolean
  readOnly?: boolean
  readOnlyEmptyMessage?: string
}>()

const emit = defineEmits<{
  loadSources: [messageId: number]
  suggestion: [value: string]
  feedback: [messageId: number, rating: FeedbackRating, comment: string | null]
  removeFeedback: [messageId: number]
}>()

const container = ref<HTMLElement | null>(null)
const expandedSourceMessageIds = ref<Set<number>>(new Set())
const editingFeedbackMessageId = ref<number | null>(null)
const feedbackCommentDraft = ref('')

watch(
  () => [props.messages.length, props.streamText],
  async () => {
    await nextTick()
    if (container.value) {
      container.value.scrollTop = container.value.scrollHeight
    }
  },
)

async function toggleSources(messageId: number): Promise<void> {
  const next = new Set(expandedSourceMessageIds.value)

  if (next.has(messageId)) {
    next.delete(messageId)
    expandedSourceMessageIds.value = next
    return
  }

  if (!props.sourcesByMessageId[messageId]) {
    emit('loadSources', messageId)
  }

  next.add(messageId)
  expandedSourceMessageIds.value = next
}

function selectRating(
  messageId: number,
  rating: FeedbackRating,
): void {
  const current = props.feedbackByMessageId[messageId]

  if (current?.rating === rating) {
    emit('removeFeedback', messageId)
    if (editingFeedbackMessageId.value === messageId) {
      editingFeedbackMessageId.value = null
      feedbackCommentDraft.value = ''
    }
    return
  }

  emit(
    'feedback',
    messageId,
    rating,
    current?.comment ?? null,
  )
}

function openFeedbackEditor(messageId: number): void {
  const current = props.feedbackByMessageId[messageId]
  if (!current) {
    return
  }
  editingFeedbackMessageId.value = messageId
  feedbackCommentDraft.value = current.comment ?? ''
}

function closeFeedbackEditor(): void {
  editingFeedbackMessageId.value = null
  feedbackCommentDraft.value = ''
}

function saveFeedbackComment(messageId: number): void {
  const current = props.feedbackByMessageId[messageId]
  if (!current) {
    return
  }
  emit(
    'feedback',
    messageId,
    current.rating,
    feedbackCommentDraft.value.trim() || null,
  )
  closeFeedbackEditor()
}

function sourceScore(source: MessageSource): string {
  if (source.similarity_score === null) {
    return ''
  }
  return `${Math.round(source.similarity_score * 100)}%`
}
</script>

<template>
  <section ref="container" class="message-scroll">
    <div v-if="loading" class="center-state">正在读取会话历史...</div>

    <div
      v-else-if="messages.length === 0 && !streaming && readOnly"
      class="center-state archived-empty"
    >
      <strong>{{ readOnlyEmptyMessage || '此归档会话暂无消息记录' }}</strong>
      <span v-if="readOnlyEmptyMessage === '暂无已归档会话'">
        归档后的历史对话会显示在左侧归档列表中。
      </span>
      <span v-else-if="readOnlyEmptyMessage === '请选择左侧归档会话查看历史记录'">
        选择一条归档记录后即可查看完整对话与知识来源。
      </span>
    </div>

    <div
      v-else-if="messages.length === 0 && !streaming"
      class="welcome-state"
    >
      <div class="welcome-orb">AI</div>
      <p class="welcome-eyebrow">企业知识库驱动</p>
      <h2>今天想咨询什么？</h2>
      <p class="welcome-copy">
        我会先检索企业知识库，再基于可靠资料回答，并展示引用来源。
      </p>

      <div class="starter-grid">
        <button type="button" @click="emit('suggestion', '退款审核通过后多久能到账？')">
          <strong>退款时效</strong>
          <span>退款审核通过后多久能到账？</span>
        </button>
        <button type="button" @click="emit('suggestion', '商品退换货需要满足哪些条件？')">
          <strong>售后政策</strong>
          <span>商品退换货需要满足哪些条件？</span>
        </button>
        <button type="button" @click="emit('suggestion', '如何联系人工客服？')">
          <strong>人工客服</strong>
          <span>如何联系人工客服？</span>
        </button>
      </div>
    </div>

    <div v-else class="message-stack">
      <article
        v-for="message in messages"
        :key="message.id"
        class="message-row"
        :class="message.role"
      >
        <div v-if="message.role === 'assistant'" class="avatar ai-avatar">AI</div>

        <div class="message-column">
          <div class="message-bubble">
            <p>{{ message.content }}</p>
          </div>

          <div
            v-if="message.role === 'assistant'"
            class="assistant-meta"
          >
            <span v-if="message.intent" class="intent-chip">
              {{ message.intent }}
            </span>
            <span
              v-if="message.routed_knowledge_base_id"
              class="route-chip"
              title="本条回答实际使用的知识库"
            >
              知识库：{{
                knowledgeBaseLabel(
                  message.routed_knowledge_base_id,
                  knowledgeBaseNamesById,
                )
              }}
            </span>
            <span v-if="message.is_fallback" class="fallback-chip">
              安全兜底
            </span>

            <div v-if="!readOnly" class="feedback-actions" aria-label="回答反馈">
              <button
                class="feedback-button"
                :class="{
                  active: feedbackByMessageId[message.id]?.rating === 1,
                }"
                type="button"
                :disabled="feedbackSubmittingMessageId === message.id"
                :aria-pressed="feedbackByMessageId[message.id]?.rating === 1"
                title="这个回答有帮助；再次点击可撤销"
                @click="selectRating(message.id, 1)"
              >
                👍 有帮助
              </button>
              <button
                class="feedback-button"
                :class="{
                  active: feedbackByMessageId[message.id]?.rating === -1,
                }"
                type="button"
                :disabled="feedbackSubmittingMessageId === message.id"
                :aria-pressed="feedbackByMessageId[message.id]?.rating === -1"
                title="这个回答没帮助；再次点击可撤销"
                @click="selectRating(message.id, -1)"
              >
                👎 没帮助
              </button>
              <button
                v-if="feedbackByMessageId[message.id]"
                class="feedback-comment-button"
                type="button"
                :disabled="feedbackSubmittingMessageId === message.id"
                @click="openFeedbackEditor(message.id)"
              >
                {{ feedbackByMessageId[message.id]?.comment ? '编辑反馈' : '补充反馈' }}
              </button>
            </div>

            <button
              class="source-toggle"
              type="button"
              @click="toggleSources(message.id)"
            >
              {{
                expandedSourceMessageIds.has(message.id)
                  ? '收起知识来源'
                  : '查看知识来源'
              }}
            </button>
          </div>

          <div
            v-if="
              message.role === 'assistant' &&
              !readOnly &&
              editingFeedbackMessageId === message.id
            "
            class="feedback-editor"
          >
            <label :for="`feedback-${message.id}`">
              文字反馈（可选）
            </label>
            <textarea
              :id="`feedback-${message.id}`"
              v-model="feedbackCommentDraft"
              maxlength="1000"
              rows="3"
              placeholder="例如：回答准确，但希望给出更具体的处理步骤。"
            ></textarea>
            <div class="feedback-editor-footer">
              <span>{{ feedbackCommentDraft.length }}/1000</span>
              <div>
                <button type="button" @click="closeFeedbackEditor">
                  取消
                </button>
                <button
                  type="button"
                  :disabled="feedbackSubmittingMessageId === message.id"
                  @click="saveFeedbackComment(message.id)"
                >
                  保存反馈
                </button>
              </div>
            </div>
          </div>

          <p
            v-else-if="
              message.role === 'assistant' &&
              feedbackByMessageId[message.id]?.comment
            "
            class="feedback-comment-summary"
          >
            你的反馈：{{ feedbackByMessageId[message.id]?.comment }}
          </p>

          <div
            v-if="
              message.role === 'assistant' &&
              expandedSourceMessageIds.has(message.id)
            "
            class="source-list"
          >
            <div
              v-if="!sourcesByMessageId[message.id]"
              class="source-loading"
            >
              正在读取来源...
            </div>

            <div
              v-else-if="(sourcesByMessageId[message.id] ?? []).length === 0"
              class="source-loading"
            >
              本条回答没有知识来源
            </div>

            <article
              v-for="source in sourcesByMessageId[message.id] ?? []"
              :key="source.id"
              class="source-card"
            >
              <div class="source-card-header">
                <span>[来源{{ source.rank }}] {{ source.document_name }}</span>
                <span>{{ sourceScore(source) }}</span>
              </div>
              <p>{{ source.chunk_summary }}</p>
            </article>
          </div>

          <div
            v-if="
              message.role === 'assistant' &&
              !readOnly &&
              message.follow_up_suggestions?.length
            "
            class="suggestion-row"
          >
            <button
              v-for="suggestion in message.follow_up_suggestions"
              :key="suggestion"
              type="button"
              @click="emit('suggestion', suggestion)"
            >
              {{ suggestion }}
            </button>
          </div>
        </div>

        <div v-if="message.role === 'user'" class="avatar user-avatar">
          你
        </div>
      </article>

      <article v-if="streaming" class="message-row assistant">
        <div class="avatar ai-avatar">AI</div>
        <div class="message-column">
          <div class="message-bubble streaming-bubble">
            <p v-if="streamText">{{ streamText }}</p>
            <div v-else class="typing-line">
              <span></span><span></span><span></span>
              <em>正在检索知识库并生成回答</em>
            </div>
            <span v-if="streamText" class="stream-caret"></span>
          </div>

          <div v-if="streamSources.length" class="source-list">
            <article
              v-for="source in streamSources"
              :key="`${source.rank}-${source.document_name}`"
              class="source-card"
            >
              <div class="source-card-header">
                <span>[来源{{ source.rank }}] {{ source.document_name }}</span>
                <span>{{ sourceScore(source) }}</span>
              </div>
              <p>{{ source.chunk_summary }}</p>
            </article>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.message-scroll {
  min-height: 0;
  overflow-y: auto;
  padding: 34px clamp(18px, 5vw, 64px) 150px;
  scroll-behavior: smooth;
}

.center-state {
  padding: 70px 0;
  color: #7b8498;
  text-align: center;
}

.archived-empty {
  display: grid;
  max-width: 520px;
  margin: 12vh auto 0;
  gap: 7px;
  padding: 28px;
  border: 1px dashed #d7deea;
  border-radius: 16px;
  background: rgb(255 255 255 / 65%);
}

.archived-empty strong {
  color: #5f6b82;
  font-size: 14px;
}

.archived-empty span {
  color: #9099aa;
  font-size: 11px;
  line-height: 1.7;
}

.welcome-state {
  max-width: 720px;
  margin: 10vh auto 0;
  text-align: center;
}

.welcome-orb {
  display: grid;
  width: 56px;
  height: 56px;
  margin: 0 auto 18px;
  place-items: center;
  border-radius: 18px;
  background: #172033;
  color: #fff;
  font-weight: 900;
  box-shadow: 0 18px 40px rgb(23 32 51 / 15%);
}

.welcome-eyebrow {
  margin: 0 0 8px;
  color: #6e7890;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .13em;
}

.welcome-state h2 {
  margin: 0 0 12px;
  font-size: clamp(27px, 5vw, 38px);
  letter-spacing: -.04em;
}

.welcome-copy {
  max-width: 560px;
  margin: 0 auto;
  color: #6e7890;
  line-height: 1.8;
}

.starter-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 34px;
}

.starter-grid button {
  display: grid;
  gap: 8px;
  padding: 18px;
  border: 1px solid #e1e6ee;
  border-radius: 15px;
  background: #fff;
  color: #273148;
  text-align: left;
  cursor: pointer;
}

.starter-grid button:hover {
  border-color: #becbf5;
  box-shadow: 0 10px 30px rgb(42 62 112 / 8%);
}

.starter-grid strong {
  font-size: 13px;
}

.starter-grid span {
  color: #778197;
  font-size: 12px;
  line-height: 1.6;
}

.message-stack {
  max-width: 920px;
  margin: 0 auto;
}

.message-row {
  display: flex;
  margin-bottom: 30px;
  align-items: flex-start;
  gap: 11px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-column {
  max-width: min(78%, 760px);
}

.message-row.user .message-column {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.avatar {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 11px;
  font-size: 11px;
  font-weight: 900;
}

.ai-avatar {
  background: #172033;
  color: #fff;
}

.user-avatar {
  background: #e5ebfb;
  color: #3159d8;
}

.message-bubble {
  padding: 13px 16px;
  border: 1px solid #e2e6ed;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(32 45 75 / 5%);
}

.user .message-bubble {
  border-color: #3159d8;
  background: #3159d8;
  color: #fff;
}

.message-bubble p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
}

.assistant-meta {
  display: flex;
  margin-top: 8px;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}

.intent-chip,
.route-chip,
.fallback-chip {
  padding: 4px 7px;
  border-radius: 7px;
  background: #f0f3f8;
  color: #738096;
  font-size: 10px;
}

.route-chip {
  background: #e9f7f0;
  color: #167a52;
  font-weight: 800;
}

.fallback-chip {
  background: #fff3e7;
  color: #aa671b;
}

.feedback-actions {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  flex-wrap: wrap;
}

.feedback-button,
.feedback-comment-button {
  padding: 4px 7px;
  border: 1px solid #e0e5ed;
  border-radius: 8px;
  background: #fff;
  color: #69758c;
  font-size: 10px;
  cursor: pointer;
}

.feedback-button:hover:not(:disabled),
.feedback-comment-button:hover:not(:disabled) {
  border-color: #b9c7ef;
  color: #3159d8;
}

.feedback-button.active {
  border-color: #b9c7ef;
  background: #edf2ff;
  color: #3159d8;
  font-weight: 800;
}

.feedback-button:disabled,
.feedback-comment-button:disabled {
  cursor: wait;
  opacity: .55;
}

.feedback-editor {
  display: grid;
  gap: 7px;
  margin-top: 10px;
  padding: 11px;
  border: 1px solid #dfe5ed;
  border-radius: 11px;
  background: #fafbfc;
}

.feedback-editor label {
  color: #59667f;
  font-size: 10px;
  font-weight: 800;
}

.feedback-editor textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid #dce2eb;
  border-radius: 9px;
  padding: 9px 10px;
  outline: none;
  background: #fff;
  color: #263149;
  font: inherit;
  font-size: 11px;
  line-height: 1.6;
}

.feedback-editor textarea:focus {
  border-color: #9fb1ec;
}

.feedback-editor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #949cad;
  font-size: 9px;
}

.feedback-editor-footer > div {
  display: flex;
  gap: 6px;
}

.feedback-editor-footer button {
  padding: 5px 9px;
  border: 1px solid #dce2eb;
  border-radius: 7px;
  background: #fff;
  color: #59667f;
  font-size: 10px;
  cursor: pointer;
}

.feedback-editor-footer button:last-child {
  border-color: #3159d8;
  background: #3159d8;
  color: #fff;
}

.feedback-comment-summary {
  margin: 8px 0 0;
  color: #7d879a;
  font-size: 10px;
  line-height: 1.6;
}

.source-toggle {
  padding: 3px 0;
  border: 0;
  background: transparent;
  color: #4864c7;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}

.source-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.source-card {
  padding: 11px 12px;
  border: 1px solid #e3e8ef;
  border-radius: 11px;
  background: #f9fafc;
}

.source-card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #44516b;
  font-size: 11px;
  font-weight: 850;
}

.source-card p {
  margin: 7px 0 0;
  color: #707b90;
  font-size: 11px;
  line-height: 1.7;
}

.source-loading {
  color: #8b94a6;
  font-size: 11px;
}

.suggestion-row {
  display: flex;
  gap: 7px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.suggestion-row button {
  padding: 7px 10px;
  border: 1px solid #dfe5ed;
  border-radius: 9px;
  background: #fff;
  color: #59667f;
  font-size: 11px;
  cursor: pointer;
}

.suggestion-row button:hover {
  border-color: #bac8ef;
  color: #3159d8;
}

.typing-line {
  display: flex;
  min-height: 24px;
  align-items: center;
  gap: 5px;
}

.typing-line span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #7184cc;
  animation: pulse 1.2s infinite ease-in-out;
}

.typing-line span:nth-child(2) {
  animation-delay: .15s;
}

.typing-line span:nth-child(3) {
  animation-delay: .3s;
}

.typing-line em {
  margin-left: 5px;
  color: #8a93a6;
  font-size: 11px;
  font-style: normal;
}

.stream-caret {
  display: inline-block;
  width: 2px;
  height: 15px;
  margin-left: 3px;
  vertical-align: -2px;
  background: #3159d8;
  animation: blink .8s infinite;
}

@keyframes pulse {
  0%, 80%, 100% { opacity: .25; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-3px); }
}

@keyframes blink {
  50% { opacity: 0; }
}

@media (max-width: 760px) {
  .starter-grid {
    grid-template-columns: 1fr;
  }

  .message-column {
    max-width: 88%;
  }
}
</style>
