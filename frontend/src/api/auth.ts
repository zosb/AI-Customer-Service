import { requestJson } from './http'
import type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  UserPublic,
} from '@/types/auth'

export function registerUser(payload: RegisterPayload): Promise<UserPublic> {
  return requestJson<UserPublic>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loginUser(payload: LoginPayload): Promise<TokenResponse> {
  return requestJson<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchCurrentUser(token: string): Promise<UserPublic> {
  return requestJson<UserPublic>(
    '/api/v1/auth/me',
    {
      method: 'GET',
    },
    token,
  )
}
