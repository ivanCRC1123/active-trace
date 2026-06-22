import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from '@/shared/services/api'
import { useSessionStore } from '@/store/sessionStore'
import { ImportarPage } from './ImportarPage'
import { ProtectedRoute } from '@/shared/components/ProtectedRoute'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const MAT = 'mat-id'
const COH = 'coh-id'
const URL_BASE = `${BASE}/v1/calificaciones/${MAT}/cohortes/${COH}`

const PREVIEW_MOCK = {
  actividades: [
    { nombre: 'Tarea 1 (Real)', tipo: 'numerica' },
    { nombre: 'Presentación', tipo: 'textual' },
  ],
  total_alumnos: 8,
  warnings: [],
}

const UMBRAL_MOCK = {
  id: null,
  asignacion_id: null,
  materia_id: MAT,
  umbral_pct: 60,
  valores_aprobatorios: ['Satisfactorio'],
  es_default: true,
}

const IMPORT_MOCK = { importadas: 16, actualizadas: 0, omitidas: 0, warnings: [] }

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

function renderPage(permissions: Record<string, string> = { 'calificaciones:importar': 'own' }) {
  useSessionStore.setState({
    accessToken: 'tok',
    user: { user_id: 'u1', tenant_id: 't1', roles: ['PROFESOR'] },
    permissions,
  })
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[`/calificaciones/${MAT}/${COH}/importar`]}>
        <Routes>
          <Route path="/login" element={<div data-testid="login" />} />
          <Route path="/403" element={<div data-testid="forbidden" />} />
          <Route element={<ProtectedRoute requiredPermission="calificaciones:importar" />}>
            <Route
              path="/calificaciones/:materiaId/:cohorteId/importar"
              element={<ImportarPage />}
            />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function uploadAndPreview(user: ReturnType<typeof userEvent.setup>) {
  server.use(
    http.post(`${URL_BASE}/preview`, () => HttpResponse.json(PREVIEW_MOCK)),
    http.get(`${URL_BASE}/umbral`, () => HttpResponse.json(UMBRAL_MOCK)),
  )
  const file = new File(['data'], 'notas.csv', { type: 'text/csv' })
  const input = screen.getByTestId('file-input')
  await user.upload(input, file)
  await user.click(screen.getByRole('button', { name: /Analizar archivo/i }))
  await screen.findByText(/alumno\(s\) detectados/i)
}

describe('ImportarPage', () => {
  it('renderiza paso 1 — zona de upload y botón analizar', () => {
    renderPage()
    expect(screen.getByText(/Importar calificaciones/i)).toBeInTheDocument()
    expect(screen.getByTestId('drop-zone')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Analizar archivo/i })).toBeDisabled()
  })

  it('paso 1: habilita botón analizar tras seleccionar un archivo', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${URL_BASE}/preview`, () => HttpResponse.json(PREVIEW_MOCK)),
      http.get(`${URL_BASE}/umbral`, () => HttpResponse.json(UMBRAL_MOCK)),
    )
    renderPage()
    const file = new File(['x'], 'notas.csv', { type: 'text/csv' })
    await user.upload(screen.getByTestId('file-input'), file)
    expect(screen.getByRole('button', { name: /Analizar archivo/i })).not.toBeDisabled()
  })

  it('paso 1 → paso 2: preview muestra actividades detectadas', async () => {
    const user = userEvent.setup()
    renderPage()
    await uploadAndPreview(user)

    expect(screen.getByLabelText('Tarea 1 (Real)')).toBeInTheDocument()
    expect(screen.getByLabelText('Presentación')).toBeInTheDocument()
    expect(screen.getByText('8 alumno(s) detectados')).toBeInTheDocument()
  })

  it('paso 2: todas las actividades marcadas por defecto', async () => {
    const user = userEvent.setup()
    renderPage()
    await uploadAndPreview(user)

    const checkboxes = screen.getAllByRole('checkbox')
    checkboxes.forEach((cb) => expect(cb).toBeChecked())
  })

  it('paso 2 → paso 3: botón continuar muestra resumen', async () => {
    const user = userEvent.setup()
    renderPage()
    await uploadAndPreview(user)

    await user.click(screen.getByRole('button', { name: /Continuar/i }))
    await screen.findByRole('button', { name: /Importar calificaciones/i })
    expect(screen.getByText(/Vas a importar/i)).toBeInTheDocument()
  })

  it('paso 3: confirmar llama importar y muestra resultado', async () => {
    const user = userEvent.setup()
    renderPage()
    await uploadAndPreview(user)

    server.use(
      http.post(`${URL_BASE}/importar`, () => HttpResponse.json(IMPORT_MOCK, { status: 201 })),
    )

    await user.click(screen.getByRole('button', { name: /Continuar/i }))
    await user.click(await screen.findByRole('button', { name: /Importar calificaciones/i }))

    await screen.findByText('Importación exitosa')
    expect(screen.getByText(/16 calificaciones importadas/i)).toBeInTheDocument()
  })

  it('error 409 no_hay_padron_activo muestra mensaje correcto', async () => {
    server.use(
      http.post(`${URL_BASE}/preview`, () =>
        HttpResponse.json({ detail: 'no_hay_padron_activo' }, { status: 409 }),
      ),
    )

    const user = userEvent.setup()
    renderPage()
    const file = new File(['x'], 'notas.csv', { type: 'text/csv' })
    await user.upload(screen.getByTestId('file-input'), file)
    await user.click(screen.getByRole('button', { name: /Analizar archivo/i }))

    await screen.findByRole('alert')
    expect(
      screen.getByText(/No hay padrón de alumnos activo/i),
    ).toBeInTheDocument()
  })

  it('error 400 sin_columna_email muestra mensaje correcto', async () => {
    server.use(
      http.post(`${URL_BASE}/preview`, () =>
        HttpResponse.json({ detail: 'sin_columna_email' }, { status: 400 }),
      ),
    )

    const user = userEvent.setup()
    renderPage()
    const file = new File(['x'], 'notas.csv')
    await user.upload(screen.getByTestId('file-input'), file)
    await user.click(screen.getByRole('button', { name: /Analizar archivo/i }))

    await waitFor(() => {
      expect(screen.getByText(/No se detectó columna de email/i)).toBeInTheDocument()
    })
  })

  it('botón vaciar abre diálogo de confirmación', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /Vaciar mis calificaciones/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/Esta acción no se puede deshacer/i)).toBeInTheDocument()
  })

  it('cancelar vaciar cierra el diálogo', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /Vaciar mis calificaciones/i }))
    await user.click(screen.getByRole('button', { name: /Cancelar/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('redirige a /403 sin permiso calificaciones:importar', () => {
    renderPage({})
    expect(screen.getByTestId('forbidden')).toBeInTheDocument()
  })
})
