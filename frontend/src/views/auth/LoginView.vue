<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import {
  normalizeAccountInput,
  validateAccountInput,
} from '@/utils/authValidation'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const account = ref('')
const password = ref('')
const errorMessage = ref('')

const canSubmit = computed(
  () =>
    account.value.trim().length > 0 &&
    password.value.length > 0 &&
    !authStore.loading,
)

async function submitLogin(): Promise<void> {
  errorMessage.value = ''

  const accountError = validateAccountInput(account.value)
  if (accountError) {
    errorMessage.value = accountError
    return
  }

  try {
    await authStore.login({
      account: normalizeAccountInput(account.value),
      password: password.value,
    })

    const redirect =
      typeof route.query.redirect === 'string'
        ? route.query.redirect
        : '/'

    await router.replace(redirect)
  } catch (error) {
    errorMessage.value = authStore.getErrorMessage(error)
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-panel">
      <div class="brand-block">
        <div class="brand-mark">AI</div>
        <div>
          <p class="brand-label">AI Customer Service</p>
          <h1>登录智能客服系统</h1>
          <p class="brand-description">
            登录后进入企业智能客服工作台，开始与知识库驱动的 AI 助手对话。
          </p>
        </div>
      </div>

      <form class="auth-form" @submit.prevent="submitLogin">
        <label class="field">
          <span>邮箱或手机号</span>
          <input
            v-model="account"
            autocomplete="username"
            placeholder="请输入邮箱或手机号"
          />
        </label>

        <label class="field">
          <span>密码</span>
          <input
            v-model="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            type="password"
          />
        </label>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>

        <button class="primary-button" :disabled="!canSubmit" type="submit">
          {{ authStore.loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <p class="auth-switch">
        还没有账号？
        <RouterLink to="/register">立即注册</RouterLink>
      </p>
    </section>
  </main>
</template>
