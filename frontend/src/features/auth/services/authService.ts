import { api } from '@/shared/services/api'
import type { User } from '@/store/sessionStore'

interface LoginSuccess {
  access_token: string
  token_type: string
  expires_in: number
}

interface LoginChallenge {
  requires_2fa: true
  session_token: string
}

export type LoginResult = LoginSuccess | LoginChallenge

export function decodeJwt(token: string): User {
  // Base64url → base64 → JSON
  const raw = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
  const payload = JSON.parse(atob(raw))
  return {
    user_id: payload.sub as string,
    tenant_id: payload.tenant_id as string,
    roles: (payload.roles ?? []) as string[],
    impersonado_id: (payload.impersonado_id as string | undefined) ?? null,
  }
}

export async function loginWithCredentials(
  email: string,
  password: string,
): Promise<LoginResult> {
  const tenant_code = (import.meta.env.VITE_DEFAULT_TENANT_CODE as string) ?? ''
  const res = await api.post<LoginResult>('/auth/login', { tenant_code, email, password })
  return res.data
}

export async function verifyTwoFA(session_token: string, code: string): Promise<LoginSuccess> {
  const res = await api.post<LoginSuccess>('/auth/2fa/verify-login', { session_token, code })
  return res.data
}

export async function fetchPermissions(accessToken: string): Promise<Record<string, string>> {
  const res = await api.get<{ permissions: Record<string, string> }>('/auth/me/permissions', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  return res.data.permissions
}

export async function logoutApi(): Promise<void> {
  await api.post('/auth/logout')
}

export async function refreshToken(): Promise<string> {
  const res = await api.post<{ access_token: string }>('/auth/refresh')
  return res.data.access_token
}

export async function forgotPassword(email: string): Promise<void> {
  await api.post('/auth/forgot', { email })
}

export async function resetPassword(token: string, new_password: string): Promise<void> {
  await api.post('/auth/reset', { token, new_password })
}
