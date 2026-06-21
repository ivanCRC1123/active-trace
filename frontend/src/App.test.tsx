import { render } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, it, expect } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import App from './App'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

// Bootstrap calls POST /auth/refresh on mount — respond immediately so the hook
// settles before the test tears down.  401 means unauthenticated → LoginPage.
const server = setupServer(
  http.post(`${BASE}/auth/refresh`, () => HttpResponse.json({}, { status: 401 })),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

it('renders App without crashing', () => {
  const { container } = render(<App />)
  // While bootstrap is in-flight the loading screen is shown — something renders.
  expect(container.firstChild).not.toBeNull()
})
