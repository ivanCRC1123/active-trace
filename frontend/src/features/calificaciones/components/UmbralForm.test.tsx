import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from '@/shared/services/api'
import { UmbralForm } from './UmbralForm'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const MAT = 'mat-id'
const COH = 'coh-id'
const UMBRAL_URL = `${BASE}/v1/calificaciones/${MAT}/cohortes/${COH}/umbral`

const UMBRAL_MOCK = {
  id: null,
  asignacion_id: null,
  materia_id: MAT,
  umbral_pct: 75,
  valores_aprobatorios: ['Aprobado', 'Distinguido'],
  es_default: false,
}

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderForm() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <UmbralForm materiaId={MAT} cohorteId={COH} />
    </QueryClientProvider>,
  )
}

describe('UmbralForm', () => {
  it('renderiza slider con min=1 y max=100', async () => {
    server.use(http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)))
    renderForm()
    const slider = await screen.findByRole('slider')
    expect(slider).toHaveAttribute('min', '1')
    expect(slider).toHaveAttribute('max', '100')
  })

  it('pre-carga el umbral_pct del servidor', async () => {
    server.use(http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)))
    renderForm()
    await waitFor(() => {
      expect(screen.getByRole('slider')).toHaveValue('75')
    })
  })

  it('pre-carga los valores aprobatorios del servidor', async () => {
    server.use(http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)))
    renderForm()
    await waitFor(() => {
      expect(screen.getByDisplayValue('Aprobado, Distinguido')).toBeInTheDocument()
    })
  })

  it('submit llama PUT /umbral con los datos actuales', async () => {
    let capturedBody: unknown
    server.use(
      http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)),
      http.put(UMBRAL_URL, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ ...UMBRAL_MOCK, es_default: false })
      }),
    )

    const user = userEvent.setup()
    renderForm()
    await screen.findByRole('slider')
    await user.click(screen.getByRole('button', { name: /guardar umbral/i }))

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ umbral_pct: 75 })
    })
  })

  it('muestra "Umbral guardado" tras éxito', async () => {
    server.use(
      http.get(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)),
      http.put(UMBRAL_URL, () => HttpResponse.json(UMBRAL_MOCK)),
    )

    const user = userEvent.setup()
    renderForm()
    await screen.findByRole('slider')
    await user.click(screen.getByRole('button', { name: /guardar umbral/i }))
    await screen.findByText('Umbral guardado')
  })
})
