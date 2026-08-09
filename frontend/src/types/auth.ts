export interface UserPublic {
  id: number
  email: string | null
  phone: string | null
  display_name: string | null
  role: 'user' | 'admin'
  status: 'active' | 'disabled'
  created_at: string
}

export interface RegisterPayload {
  account: string
  password: string
  display_name?: string | null
}

export interface LoginPayload {
  account: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserPublic
}
