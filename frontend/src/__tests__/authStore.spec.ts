import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as authApi from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import type { UserPublic } from '@/types/auth'

const user: UserPublic = {
  id: 7,
  email: 'tester@example.com',
  phone: null,
  display_name: '测试用户',
  role: 'user',
  status: 'active',
  created_at: '2026-08-07T00:00:00',
}

describe('auth store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('stores token and user after login', async () => {
    vi.spyOn(authApi, 'loginUser').mockResolvedValue({
      access_token: 'test-token',
      token_type: 'bearer',
      expires_in: 7200,
      user,
    })

    const store = useAuthStore()

    await store.login({
      account: 'tester@example.com',
      password: 'StrongPass1!',
    })

    expect(store.token).toBe('test-token')
    expect(store.user?.id).toBe(7)
    expect(store.isAuthenticated).toBe(true)
    expect(localStorage.getItem('ai_customer_service_access_token')).toBe(
      'test-token',
    )
  })

  it('clears authentication state on logout', async () => {
    vi.spyOn(authApi, 'loginUser').mockResolvedValue({
      access_token: 'test-token',
      token_type: 'bearer',
      expires_in: 7200,
      user,
    })

    const store = useAuthStore()
    await store.login({
      account: 'tester@example.com',
      password: 'StrongPass1!',
    })

    store.logout()

    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('ai_customer_service_access_token')).toBeNull()
  })

  it('restores current user from stored token', async () => {
    localStorage.setItem(
      'ai_customer_service_access_token',
      'stored-token',
    )
    vi.spyOn(authApi, 'fetchCurrentUser').mockResolvedValue(user)

    setActivePinia(createPinia())
    const store = useAuthStore()

    await store.initialize()

    expect(store.token).toBe('stored-token')
    expect(store.user?.email).toBe('tester@example.com')
    expect(store.isAuthenticated).toBe(true)
  })

  it('drops an invalid stored token', async () => {
    localStorage.setItem(
      'ai_customer_service_access_token',
      'expired-token',
    )
    vi.spyOn(authApi, 'fetchCurrentUser').mockRejectedValue(
      new Error('expired'),
    )

    setActivePinia(createPinia())
    const store = useAuthStore()

    await store.initialize()

    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })
})
