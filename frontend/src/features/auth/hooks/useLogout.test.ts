import { renderHook, act } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { useLogout } from './useLogout'
import { useSessionStore } from '@/store/sessionStore'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
  vi.unstubAllGlobals()
})
afterAll(() => server.close())

describe('useLogout', () => {
  it('clears session and redirects to /login after successful logout', async () => {
    const mockLocation = { href: 'http://localhost/', pathname: '/' }
    vi.stubGlobal('location', mockLocation)

    useSessionStore.setState({
      accessToken: 'valid-token',
      user: { user_id: 'u1', tenant_id: 't1', roles: ['ADMIN'] },
      permissions: { 'usuarios:leer': 'all' },
    })

    server.use(
      http.post(`${BASE}/auth/logout`, () => HttpResponse.json({ detail: 'Logged out successfully.' })),
    )

    const { result } = renderHook(() => useLogout())
    await act(async () => {
      await result.current()
    })

    expect(useSessionStore.getState().accessToken).toBeNull()
    expect(useSessionStore.getState().user).toBeNull()
    expect(mockLocation.href).toBe('/login')
  })

  it('clears session even if /logout request fails', async () => {
    const mockLocation = { href: 'http://localhost/', pathname: '/' }
    vi.stubGlobal('location', mockLocation)

    useSessionStore.setState({
      accessToken: 'valid-token',
      user: { user_id: 'u1', tenant_id: 't1', roles: ['ADMIN'] },
      permissions: {},
    })

    server.use(
      http.post(`${BASE}/auth/logout`, () => HttpResponse.json({}, { status: 500 })),
    )

    const { result } = renderHook(() => useLogout())
    await act(async () => {
      await result.current()
    })

    expect(useSessionStore.getState().accessToken).toBeNull()
    expect(mockLocation.href).toBe('/login')
  })
})
