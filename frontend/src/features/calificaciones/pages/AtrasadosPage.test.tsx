import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from '@/shared/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { AtrasadosPage } from './AtrasadosPage'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const MAT = 'mat-id'
const COH = 'coh-id'
const ANALISIS_URL = `${BASE}/v1/analisis/${MAT}/cohortes/${COH}/atrasados`

const MOCK_DATA = {
  total_alumnos: 10,
  total_atrasados: 2,
  atrasados: [
    {
      entrada_padron_id: 'ep-1',
      nombre: 'Juan',
      apellidos: 'García',
      comision: 'A',
      regional: 'CABA',
      actividades_faltantes: ['Tarea 1', 'Tarea 2'],
      actividades_bajo_umbral: ['Parcial 1'],
    },
    {
      entrada_padron_id: 'ep-2',
      nombre: 'Ana',
      apellidos: 'López',
      comision: 'B',
      regional: null,
      actividades_faltantes: [],
      actividades_bajo_umbral: ['TP Final'],
    },
  ],
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

function renderPage(permissions: Record<string, string> = { 'atrasados:ver': 'own' }) {
  useSessionStore.setState({
    accessToken: 'tok',
    user: { user_id: 'u1', tenant_id: 't1', roles: ['PROFESOR'] },
    permissions,
  })
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[`/calificaciones/${MAT}/${COH}/atrasados`]}>
        <Routes>
          <Route
            path="/calificaciones/:materiaId/:cohorteId/atrasados"
            element={<AtrasadosPage />}
          />
          <Route path="/comunicaciones/nuevo" element={<div data-testid="comunicaciones-nuevo" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AtrasadosPage', () => {
  it('muestra tabla con datos de atrasados', async () => {
    server.use(http.get(ANALISIS_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage()
    await screen.findByText('García')
    expect(screen.getByText('López')).toBeInTheDocument()
    expect(screen.getByText('2 alumno(s) atrasados de 10')).toBeInTheDocument()
  })

  it('empty state "todos al día" cuando atrasados=[] y total_alumnos>0', async () => {
    server.use(
      http.get(ANALISIS_URL, () =>
        HttpResponse.json({ total_alumnos: 10, total_atrasados: 0, atrasados: [] }),
      ),
    )
    renderPage()
    await screen.findByText('Todos los alumnos están al día')
  })

  it('empty state "sin calificaciones" cuando total_alumnos=0', async () => {
    server.use(
      http.get(ANALISIS_URL, () =>
        HttpResponse.json({ total_alumnos: 0, total_atrasados: 0, atrasados: [] }),
      ),
    )
    renderPage()
    await screen.findByText(/No hay calificaciones importadas/i)
  })

  it('botón "Enviar comunicación" deshabilitado sin selección', async () => {
    server.use(http.get(ANALISIS_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage({ 'atrasados:ver': 'own', 'comunicacion:enviar': 'own' })
    await screen.findByText('García')
    expect(screen.getByRole('button', { name: /Enviar comunicación/i })).toBeDisabled()
  })

  it('botón "Enviar comunicación" oculto sin permiso comunicacion:enviar', async () => {
    server.use(http.get(ANALISIS_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage({ 'atrasados:ver': 'own' })
    await screen.findByText('García')
    expect(screen.queryByRole('button', { name: /Enviar comunicación/i })).not.toBeInTheDocument()
  })

  it('seleccionar fila y hacer click navega a comunicaciones/nuevo', async () => {
    const user = userEvent.setup()
    server.use(http.get(ANALISIS_URL, () => HttpResponse.json(MOCK_DATA)))
    renderPage({ 'atrasados:ver': 'own', 'comunicacion:enviar': 'own' })
    await screen.findByText('García')
    await user.click(screen.getByLabelText(/Seleccionar García/))
    await user.click(screen.getByRole('button', { name: /Enviar comunicación/i }))
    await screen.findByTestId('comunicaciones-nuevo')
  })
})
