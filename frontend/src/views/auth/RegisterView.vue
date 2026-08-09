<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import {
  normalizeAccountInput,
  validateAccountInput,
  validatePassword,
} from '@/utils/authValidation'

const authStore = useAuthStore()
const router = useRouter()

const account = ref('')
const displayName = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const canSubmit = computed(
  () =>
    account.value.trim().length > 0 &&
    password.value.length > 0 &&
    confirmPassword.value.length > 0 &&
    !authStore.loading,
)

async function submitRegister(): Promise<void> {
  errorMessage.value = ''
  successMessage.value = ''

  const accountError = validateAccountInput(account.value)
  if (accountError) {
    errorMessage.value = accountError
    return
  }

  const passwordResult = validatePassword(password.value)
  if (!passwordResult.valid) {
    errorMessage.value = passwordResult.message
    return
  }

  if (password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  try {
    await authStore.register({
      account: normalizeAccountInput(account.value),
      password: password.value,
      display_name: displayName.value.trim() || null,
    })

    successMessage.value = '注册成功，即将前往登录'
    await router.push({
      name: 'login',
      query: {
        registered: '1',
        account: normalizeAccountInput(account.value),
      },
    })
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
          <h1>创建账号</h1>
          <p class="brand-description">
            支持邮箱或手机号注册。密码需要同时包含大小写字母、数字和特殊字符。
          </p>
        </div>
      </div>

      <form class="auth-form" @submit.prevent="submitRegister">
        <label class="field">
          <span>邮箱或手机号</span>
          <input
            v-model="account"
            autocomplete="username"
            placeholder="例如：user@example.com"
          />
        </label>

        <label class="field">
          <span>显示名称（可选）</span>
          <input
            v-model="displayName"
            maxlength="64"
            placeholder="请输入显示名称"
          />
        </label>

        <label class="field">
          <span>密码</span>
          <input
            v-model="password"
            autocomplete="new-password"
            placeholder="至少 8 位，包含大小写字母、数字和符号"
            type="password"
          />
        </label>

        <label class="field">
          <span>确认密码</span>
          <input
            v-model="confirmPassword"
            autocomplete="new-password"
            placeholder="请再次输入密码"
            type="password"
          />
        </label>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>
        <p v-if="successMessage" class="form-success">
          {{ successMessage }}
        </p>

        <button class="primary-button" :disabled="!canSubmit" type="submit">
          {{ authStore.loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="auth-switch">
        已有账号？
        <RouterLink to="/login">返回登录</RouterLink>
      </p>
    </section>
  </main>
</template>
