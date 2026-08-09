import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  fetchCurrentUser,
  loginUser,
  registerUser,
} from '@/api/auth'
import { ApiError } from '@/api/http'
import type {
  LoginPayload,
  RegisterPayload,
  UserPublic,
} from '@/types/auth'

const TOKEN_STORAGE_KEY = 'ai_customer_service_access_token'

function readStoredToken(): string | null {
  if (typeof localStorage === 'undefined') {
    return null
  }
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(readStoredToken())
  const user = ref<UserPublic | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  const isAuthenticated = computed(
    () => Boolean(token.value && user.value),
  )

  function persistToken(nextToken: string | null): void {
    token.value = nextToken

    if (typeof localStorage === 'undefined') {
      return
    }

    if (nextToken) {
      localStorage.setItem(TOKEN_STORAGE_KEY, nextToken)
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
    }
  }

  function logout(): void {
    persistToken(null)
    user.value = null
    initialized.value = true
  }

  async function initialize(): Promise<void> {
    if (initialized.value) {
      return
    }

    if (!token.value) {
      user.value = null
      initialized.value = true
      return
    }

    try {
      user.value = await fetchCurrentUser(token.value)
    } catch {
      logout()
    } finally {
      initialized.value = true
    }
  }

  async function login(payload: LoginPayload): Promise<void> {
    loading.value = true
    try {
      const result = await loginUser(payload)
      persistToken(result.access_token)
      user.value = result.user
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  async function register(payload: RegisterPayload): Promise<UserPublic> {
    loading.value = true
    try {
      return await registerUser(payload)
    } finally {
      loading.value = false
    }
  }

  function getErrorMessage(error: unknown): string {
    if (error instanceof ApiError) {
      return error.detail
    }
    return '操作失败，请稍后重试'
  }

  return {
    token,
    user,
    initialized,
    loading,
    isAuthenticated,
    initialize,
    login,
    register,
    logout,
    getErrorMessage,
  }
})
