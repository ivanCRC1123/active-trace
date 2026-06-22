import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { CalificacionesHomePage } from './CalificacionesHomePage'
import { ProtectedRoute } from '@/shared/components/ProtectedRoute'
import { useSessionStore } from '@/store/sessionStore'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
})
afterAll(() => server.close())

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage(permissions: Record<string, string> = {}) {
  useSessionStore.setState({
    accessToken: 'tok',
    user: { user_id: 'u1', tenant_id: 't1', roles: ['PROFESOR'] },
    permissions,
  })
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={['/calificaciones']}>
        <Routes>
          <Route path="/login" element={<div data-testid="login">Login</div>} />
          <Route path="/403" element={<div data-testid="forbidden">Forbidden</div>} />
          <Route element={<ProtectedRoute requiredPermission="calificaciones:importar" />}>
            <Route path="/calificaciones" element={<CalificacionesHomePage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const ASIGNACIONES_MOCK = [
  {
    id: 'asig-1',
    materia_id: 'mat-1',
    materia_nombre: 'Programación I',
    carrera_id: 'car-1',
    carrera_nombre: 'Ingeniería',
    cohorte_id: 'coh-1',
    cohorte_nombre: '2024-1',
    comisiones: [],
    rol_nombre: 'PROFESOR',
    desde: '2024-01-01',
    hasta: null,
  },
  {
    id: 'asig-2',
    materia_id: 'mat-2',
    materia_nombre: 'Bases de Datos',
    carrera_id: 'car-1',
    carrera_nombre: 'Ingeniería',
    cohorte_id: 'coh-2',
    cohorte_nombre: '2024-2',
    comisiones: [],
    rol_nombre: 'PROFESOR',
    desde: '2024-01-01',
    hasta: null,
  },
]

describe('CalificacionesHomePage', () => {
  it('redirige a /login cuando no hay sesión', () => {
    render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter initialEntries={['/calificaciones']}>
          <Routes>
            <Route path="/login" element={<div data-testid="login">Login</div>} />
            <Route path="/403" element={<div data-testid="forbidden">Forbidden</div>} />
            <Route element={<ProtectedRoute requiredPermission="calificaciones:importar" />}>
              <Route path="/calificaciones" element={<CalificacionesHomePage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByTestId('login')).toBeInTheDocument()
  })

  it('redirige a /403 cuando falta el permiso calificaciones:importar', () => {
    renderPage({})
    expect(screen.getByTestId('forbidden')).toBeInTheDocument()
  })

  it('renderiza la lista de materias con datos de /me/asignaciones', async () => {
    server.use(
      http.get(`${BASE}/v1/me/asignaciones`, () => HttpResponse.json(ASIGNACIONES_MOCK)),
    )
    renderPage({ 'calificaciones:importar': 'own' })
    await waitFor(() => {
      expect(screen.getByText('Programación I')).toBeInTheDocument()
      expect(screen.getByText('Bases de Datos')).toBeInTheDocument()
    })
  })

  it('cada materia es un link a /calificaciones/:mid/:cid', async () => {
    server.use(
      http.get(`${BASE}/v1/me/asignaciones`, () => HttpResponse.json(ASIGNACIONES_MOCK)),
    )
    renderPage({ 'calificaciones:importar': 'own' })
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /Programación I/i })).toHaveAttribute(
        'href',
        '/calificaciones/mat-1/coh-1',
      )
    })
  })

  it('muestra estado vacío cuando la lista está vacía', async () => {
    server.use(
      http.get(`${BASE}/v1/me/asignaciones`, () => HttpResponse.json([])),
    )
    renderPage({ 'calificaciones:importar': 'own' })
    await waitFor(() => {
      expect(screen.getByText('Sin materias asignadas')).toBeInTheDocument()
    })
  })

  it('muestra estado vacío cuando las asignaciones no tienen materia_id o cohorte_id', async () => {
    server.use(
      http.get(`${BASE}/v1/me/asignaciones`, () =>
        HttpResponse.json([
          { ...ASIGNACIONES_MOCK[0], materia_id: null },
          { ...ASIGNACIONES_MOCK[1], cohorte_id: null },
        ]),
      ),
    )
    renderPage({ 'calificaciones:importar': 'own' })
    await waitFor(() => {
      expect(screen.getByText('Sin materias asignadas')).toBeInTheDocument()
    })
  })
})
