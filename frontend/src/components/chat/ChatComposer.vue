<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  disabled: boolean
  streaming: boolean
  dailyQuestionCount: number | null
  suggestedQuestion: string
}>()

const emit = defineEmits<{
  send: [value: string]
  stop: []
  consumedSuggestion: []
}>()

const value = ref('')

watch(
  () => props.suggestedQuestion,
  (next) => {
    if (!next) {
      return
    }
    value.value = next
    emit('consumedSuggestion')
  },
)

const remaining = computed(
  () =>
    props.dailyQuestionCount === null
      ? null
      : Math.max(0, 100 - props.dailyQuestionCount),
)

function submit(): void {
  const question = value.value.trim()
  if (!question || props.disabled) {
    return
  }

  emit('send', question)
  value.value = ''
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }

  event.preventDefault()
  submit()
}
</script>

<template>
  <div class="composer-shell">
    <div class="composer-box">
      <textarea
        v-model="value"
        :disabled="disabled"
        maxlength="500"
        rows="1"
        placeholder="向 AI 客服提问，Enter 发送，Shift + Enter 换行..."
        @keydown="onKeydown"
      ></textarea>

      <div class="composer-footer">
        <div class="composer-hints">
          <span>{{ value.length }}/500</span>
          <span v-if="remaining !== null">
            今日剩余约 {{ remaining }} 次
          </span>
        </div>

        <button
          v-if="streaming"
          class="stop-button"
          type="button"
          @click="emit('stop')"
        >
          ■ 停止
        </button>
        <button
          v-else
          class="send-button"
          type="button"
          :disabled="disabled || !value.trim()"
          @click="submit"
        >
          发送
          <span>↗</span>
        </button>
      </div>
    </div>

    <p class="composer-note">
      AI 回答仅依据已检索到的企业知识库内容；重要业务信息请以正式政策为准。
    </p>
  </div>
</template>

<style scoped>
.composer-shell {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  padding: 18px clamp(18px, 5vw, 64px) 15px;
  background:
    linear-gradient(to top, #f5f7fb 72%, rgb(245 247 251 / 0%));
}

.composer-box {
  max-width: 920px;
  margin: 0 auto;
  padding: 11px 12px 9px 15px;
  border: 1px solid #d9e0ea;
  border-radius: 17px;
  background: #fff;
  box-shadow: 0 14px 42px rgb(34 47 79 / 11%);
}

textarea {
  width: 100%;
  min-height: 52px;
  max-height: 160px;
  resize: vertical;
  border: 0;
  outline: 0;
  background: transparent;
  color: #172033;
  line-height: 1.65;
}

textarea::placeholder {
  color: #9aa2b2;
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer-hints {
  display: flex;
  gap: 13px;
  color: #929aab;
  font-size: 10px;
}

.send-button,
.stop-button {
  min-width: 82px;
  min-height: 36px;
  border: 0;
  border-radius: 10px;
  font-weight: 800;
  cursor: pointer;
}

.send-button {
  background: #3159d8;
  color: #fff;
}

.send-button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.stop-button {
  background: #edf0f5;
  color: #374158;
}

.composer-note {
  max-width: 920px;
  margin: 7px auto 0;
  color: #9aa2b2;
  font-size: 9px;
  text-align: center;
}
</style>
