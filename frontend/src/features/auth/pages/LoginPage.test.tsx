import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { LoginPage } from './LoginPage'
import { useSessionStore } from '@/store/sessionStore'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

// Build a minimal JWT with the claims create_access_token produces.
// atob/btoa are available in jsdom.
function makeJwt(payload: object): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-sig`
}

const MOCK_TOKEN = makeJwt({
  sub: 'user-uuid-1',
  tenant_id: 'tenant-uuid-1',
  roles: ['ADMIN'],
})

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
})
afterAll(() => server.close())

// Renders LoginPage with a "/dashboard" stub so navigate('/') works in tests.
function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div data-testid="dashboard">Dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  it('renders the credentials form', () => {
    renderLogin()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Contraseña')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ingresar' })).toBeInTheDocument()
  })

  it('transitions to AWAITING_2FA when server returns requires_2fa', async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ requires_2fa: true, session_token: 'sess-abc' }),
      ),
    )

    renderLogin()
    await userEvent.type(screen.getByLabelText('Email'), 'user@test.com')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'secret')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Código de verificación')).toBeInTheDocument(),
    )
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
  })

  it('sets session and redirects after 2FA verification succeeds', async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ requires_2fa: true, session_token: 'sess-abc' }),
      ),
      http.post(`${BASE}/auth/2fa/verify-login`, () =>
        HttpResponse.json({ access_token: MOCK_TOKEN, token_type: 'bearer', expires_in: 900 }),
      ),
      http.get(`${BASE}/auth/me/permissions`, () =>
        HttpResponse.json({ permissions: { 'usuarios:leer': 'all' } }),
      ),
    )

    renderLogin()
    await userEvent.type(screen.getByLabelText('Email'), 'user@test.com')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'secret')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))

    await waitFor(() => screen.getByLabelText('Código de verificación'))
    await userEvent.type(screen.getByLabelText('Código de verificación'), '123456')
    await userEvent.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => {
      const state = useSessionStore.getState()
      expect(state.accessToken).toBe(MOCK_TOKEN)
      expect(state.user?.user_id).toBe('user-uuid-1')
      expect(state.user?.tenant_id).toBe('tenant-uuid-1')
      expect(state.permissions).toEqual({ 'usuarios:leer': 'all' })
    })

    // navigate('/', { replace: true }) renders the dashboard stub
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument())
  })

  it('sets session and redirects on direct login (no 2FA)', async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ access_token: MOCK_TOKEN, token_type: 'bearer', expires_in: 900 }),
      ),
      http.get(`${BASE}/auth/me/permissions`, () =>
        HttpResponse.json({ permissions: { 'tareas:leer': 'own' } }),
      ),
    )

    renderLogin()
    await userEvent.type(screen.getByLabelText('Email'), 'user@test.com')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'secret')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))

    await waitFor(() => {
      expect(useSessionStore.getState().accessToken).toBe(MOCK_TOKEN)
      expect(useSessionStore.getState().permissions).toEqual({ 'tareas:leer': 'own' })
    })
    await waitFor(() => expect(screen.getByTestId('dashboard')).toBeInTheDocument())
  })
})
