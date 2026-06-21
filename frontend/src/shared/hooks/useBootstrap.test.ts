import { renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { useBootstrap } from './useBootstrap'
import { useSessionStore } from '@/store/sessionStore'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

function makeJwt(payload: object): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-sig`
}

const MOCK_TOKEN = makeJwt({
  sub: 'user-uuid-1',
  tenant_id: 'tenant-uuid-1',
  roles: ['COORDINADOR'],
})

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
  vi.unstubAllGlobals()
})
afterAll(() => server.close())

describe('useBootstrap', () => {
  it('starts as bootstrapping = true', () => {
    // /auth/refresh never resolves — just check initial state
    server.use(
      http.post(`${BASE}/auth/refresh`, () => new Promise(() => {})), // pending forever
    )
    const { result } = renderHook(() => useBootstrap())
    expect(result.current).toBe(true)
  })

  it('restores session when /auth/refresh succeeds', async () => {
    server.use(
      http.post(`${BASE}/auth/refresh`, () =>
        HttpResponse.json({ access_token: MOCK_TOKEN, token_type: 'bearer', expires_in: 900 }),
      ),
      http.get(`${BASE}/auth/me/permissions`, () =>
        HttpResponse.json({ permissions: { 'alumnos:leer': 'all' } }),
      ),
    )

    const { result } = renderHook(() => useBootstrap())

    await waitFor(() => expect(result.current).toBe(false))

    const state = useSessionStore.getState()
    expect(state.accessToken).toBe(MOCK_TOKEN)
    expect(state.user?.user_id).toBe('user-uuid-1')
    expect(state.user?.tenant_id).toBe('tenant-uuid-1')
    expect(state.user?.roles).toEqual(['COORDINADOR'])
    expect(state.permissions).toEqual({ 'alumnos:leer': 'all' })
  })

  it('remains unauthenticated when /auth/refresh fails', async () => {
    // Stub location so the interceptor's redirect doesn't throw in jsdom
    const mockLocation = { href: 'http://localhost/login', pathname: '/login' }
    vi.stubGlobal('location', mockLocation)

    server.use(
      http.post(`${BASE}/auth/refresh`, () => HttpResponse.json({}, { status: 401 })),
    )

    const { result } = renderHook(() => useBootstrap())

    await waitFor(() => expect(result.current).toBe(false))

    expect(useSessionStore.getState().accessToken).toBeNull()
    expect(useSessionStore.getState().user).toBeNull()
  })
})
