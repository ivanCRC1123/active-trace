import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from '@/shared/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { NotasFinalesPage } from './NotasFinalesPage'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const MAT = 'mat-id'
const COH = 'coh-id'
const ANALISIS_BASE = `${BASE}/v1/analisis/${MAT}/cohortes/${COH}`
const UMBRAL_URL = `${BASE}/v1/calificaciones/${MAT}/cohortes/${COH}/umbral`

const UMBRAL_MOCK = {
  id: null,
  asignacion_id: null,
  materia_id: MAT,
  umbral_pct: 60,
  valores_aprobatorios: ['Satisfactorio'],
  es_default: true,
}

const NOTAS_MOCK = {
  items: [
    {
      entrada_padron_id: 'ep-1',
      nombre: 'Juan',
      apellidos: 'García',
      comision: 'A',
      aprobadas: 8,
      total_calificaciones: 10,
      pct_actividades_aprobadas: 80.0,
    },
    {
      entrada_padron_id: 'ep-2',
      nombre: 'Ana',
      apellidos: 'López',
      comision: 'B',
      aprobadas: 0,
      total_calificaciones: 0,
      pct_actividades_aprobadas: null,
    },
  ],
  total_alumnos: 2,
}

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
  vi.restoreAllMocks()
})
afterAll(() => server.close())

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  useSessionStore.setState({
    accessToken: 'tok',
    user: { user_id: 'u1', tenant_id: 't1', roles: ['PROFESOR'] },
    permissions: { 'atrasados:ver': 'own' },
  })
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[`/calificaciones/${MAT}/${COH}/notas-finales`]}>
        <Routes>
          <Route
            path="/calificaciones/:materiaId/:cohorteId/notas-finales"
            element={<NotasFinalesPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mockDefaultHandlers() {
  server.use(
    http.get(`${ANALISIS_BASE}/notas-finales`, () => HttpResponse.json(NOTAS_MOCK)),
    http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)),
  )
}

describe('NotasFinalesPage', () => {
  it('muestra tabla con notas finales', async () => {
    mockDefaultHandlers()
    renderPage()
    await screen.findByText('García')
    expect(screen.getByText('López')).toBeInTheDocument()
    expect(screen.getByText('2 alumno(s)')).toBeInTheDocument()
  })

  it('pct_actividades_aprobadas=null muestra "—"', async () => {
    mockDefaultHandlers()
    renderPage()
    await screen.findByText('García')
    // López has pct=null → "—" in Nota Final column
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('pct_actividades_aprobadas muestra con formato "80.00 %"', async () => {
    mockDefaultHandlers()
    renderPage()
    await screen.findByText('80.00 %')
  })

  it('botón Exportar CSV dispara descarga con Axios blob', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    URL.revokeObjectURL = vi.fn()
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})

    mockDefaultHandlers()
    server.use(
      http.get(`${ANALISIS_BASE}/notas-finales/exportar`, () =>
        new HttpResponse('col1,col2\nv1,v2\n', {
          headers: { 'Content-Type': 'text/csv' },
        }),
      ),
    )

    const user = userEvent.setup()
    renderPage()
    await screen.findByText('García')
    await user.click(screen.getByRole('button', { name: /Exportar CSV/i }))

    await vi.waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled())
    expect(clickSpy).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })

  it('empty state cuando no hay items', async () => {
    server.use(
      http.get(`${ANALISIS_BASE}/notas-finales`, () =>
        HttpResponse.json({ items: [], total_alumnos: 0 }),
      ),
      http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)),
    )
    renderPage()
    await screen.findByText(/No hay notas finales disponibles/i)
  })
})
