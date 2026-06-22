import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from '@/shared/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { RankingPage } from './RankingPage'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const MAT = 'mat-id'
const COH = 'coh-id'
const RANKING_URL = `${BASE}/v1/analisis/${MAT}/cohortes/${COH}/ranking`

const MOCK_DATA = {
  items: [
    {
      posicion: 1,
      entrada_padron_id: 'ep-1',
      nombre: 'Juan',
      apellidos: 'García',
      comision: 'A',
      total_aprobadas: 9,
      total_calificaciones: 10,
    },
    {
      posicion: 2,
      entrada_padron_id: 'ep-2',
      nombre: 'Ana',
      apellidos: 'López',
      comision: 'B',
      total_aprobadas: 8,
      total_calificaciones: 10,
    },
    {
      posicion: 3,
      entrada_padron_id: 'ep-3',
      nombre: 'Pedro',
      apellidos: 'Martínez',
      comision: 'A',
      total_aprobadas: 7,
      total_calificaciones: 10,
    },
  ],
  total_incluidos: 3,
  total_excluidos: 1,
}

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

function renderPage() {
  useSessionStore.setState({
    accessToken: 'tok',
    user: { user_id: 'u1', tenant_id: 't1', roles: ['PROFESOR'] },
    permissions: { 'atrasados:ver': 'own' },
  })
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[`/calificaciones/${MAT}/${COH}/ranking`]}>
        <Routes>
          <Route
            path="/calificaciones/:materiaId/:cohorteId/ranking"
            element={<RankingPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RankingPage', () => {
  it('muestra tabla con datos de ranking', async () => {
    server.use(http.get(RANKING_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage()
    await screen.findByText('García')
    expect(screen.getByText('López')).toBeInTheDocument()
    expect(screen.getByText('Martínez')).toBeInTheDocument()
  })

  it('muestra porcentaje calculado correctamente', async () => {
    server.use(http.get(RANKING_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage()
    await screen.findByText('90.0%')
    expect(screen.getByText('80.0%')).toBeInTheDocument()
    expect(screen.getByText('70.0%')).toBeInTheDocument()
  })

  it('muestra badges de posición 1, 2 y 3', async () => {
    server.use(http.get(RANKING_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage()
    await screen.findByText('García')
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('muestra footer con total_incluidos y total_excluidos', async () => {
    server.use(http.get(RANKING_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage()
    await screen.findByText(/3 alumnos incluidos/)
    expect(screen.getByText(/1 excluidos sin ninguna aprobada/)).toBeInTheDocument()
  })

  it('empty state cuando no hay items', async () => {
    server.use(
      http.get(RANKING_URL, () =>
        HttpResponse.json({ items: [], total_incluidos: 0, total_excluidos: 0 }),
      ),
    )
    renderPage()
    await screen.findByText(/No hay ranking disponible/i)
  })
})
