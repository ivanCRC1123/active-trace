import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from './api'
import { useSessionStore } from '@/store/sessionStore'

// MSW intercepts XHR/fetch in jsdom via @mswjs/interceptors.
// Force an absolute baseURL so axios builds absolute request URLs that
// MSW can pattern-match; a relative baseURL ('/api') stays relative in Node
// and MSW never sees 'http://localhost/api/…'.
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

describe('request interceptor', () => {
  it('attaches Authorization: Bearer when session has an accessToken', async () => {
    useSessionStore.setState({ accessToken: 'tok-abc', user: null, permissions: {} })

    let captured: string | null = null
    server.use(
      http.get(`${BASE}/data`, ({ request }) => {
        captured = request.headers.get('Authorization')
        return HttpResponse.json({ ok: true })
      }),
    )

    await api.get('/data')
    expect(captured).toBe('Bearer tok-abc')
  })

  it('sends no Authorization header when store has no token', async () => {
    let captured: string | null = 'sentinel'
    server.use(
      http.get(`${BASE}/data`, ({ request }) => {
        captured = request.headers.get('Authorization')
        return HttpResponse.json({ ok: true })
      }),
    )

    await api.get('/data')
    expect(captured).toBeNull()
  })
})

describe('response interceptor — 401 transparent refresh', () => {
  it('401 triggers refresh, updates token, and retries the original request', async () => {
    useSessionStore.setState({ accessToken: 'old-tok', user: null, permissions: {} })

    server.use(
      http.get(`${BASE}/resource`, ({ request }) => {
        const auth = request.headers.get('Authorization')
        if (auth === 'Bearer old-tok') return HttpResponse.json({}, { status: 401 })
        return HttpResponse.json({ value: 42 })
      }),
      http.post(`${BASE}/auth/refresh`, () =>
        HttpResponse.json({ access_token: 'new-tok', token_type: 'bearer', expires_in: 900 }),
      ),
    )

    const res = await api.get('/resource')
    expect(res.data).toEqual({ value: 42 })
    expect(useSessionStore.getState().accessToken).toBe('new-tok')
  })

  it('CONCURRENT: 3 simultaneous 401s call /auth/refresh exactly once', async () => {
    useSessionStore.setState({ accessToken: 'old-tok', user: null, permissions: {} })
    let refreshCount = 0

    server.use(
      http.get(`${BASE}/item`, ({ request }) => {
        const auth = request.headers.get('Authorization')
        if (auth === 'Bearer old-tok') return HttpResponse.json({}, { status: 401 })
        return HttpResponse.json({ ok: true })
      }),
      http.post(`${BASE}/auth/refresh`, async () => {
        refreshCount++
        // Delay long enough for all three interceptors to reach the
        // "await refreshPromise" point before the refresh resolves.
        await new Promise((r) => setTimeout(r, 30))
        return HttpResponse.json({ access_token: 'new-tok', token_type: 'bearer', expires_in: 900 })
      }),
    )

    const [r1, r2, r3] = await Promise.all([api.get('/item'), api.get('/item'), api.get('/item')])

    expect(refreshCount).toBe(1)
    expect(r1.data).toEqual({ ok: true })
    expect(r2.data).toEqual({ ok: true })
    expect(r3.data).toEqual({ ok: true })
  })

  it('/auth/refresh returning 401 clears session and does not loop', async () => {
    useSessionStore.setState({ accessToken: 'stale-tok', user: null, permissions: {} })
    // Give the stub a valid origin so jsdom can still resolve URLs internally.
    const mockLocation = { href: 'http://localhost/' }
    vi.stubGlobal('location', mockLocation)

    server.use(
      http.get(`${BASE}/secret`, () => HttpResponse.json({}, { status: 401 })),
      http.post(`${BASE}/auth/refresh`, () => HttpResponse.json({}, { status: 401 })),
    )

    await expect(api.get('/secret')).rejects.toMatchObject({ response: { status: 401 } })

    expect(useSessionStore.getState().accessToken).toBeNull()
    expect(mockLocation.href).toBe('/login')
  })
})

describe('response interceptor — 403 pass-through', () => {
  it('403 is passed through without calling /auth/refresh', async () => {
    useSessionStore.setState({ accessToken: 'tok', user: null, permissions: {} })
    let refreshCalled = false

    server.use(
      http.get(`${BASE}/admin`, () => HttpResponse.json({ detail: 'Forbidden' }, { status: 403 })),
      http.post(`${BASE}/auth/refresh`, () => {
        refreshCalled = true
        return HttpResponse.json({ access_token: 'new', token_type: 'bearer', expires_in: 900 })
      }),
    )

    await expect(api.get('/admin')).rejects.toMatchObject({ response: { status: 403 } })
    expect(refreshCalled).toBe(false)
  })
})
