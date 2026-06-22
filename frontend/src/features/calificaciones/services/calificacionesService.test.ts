import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { api } from '@/shared/services/api'
import { calificacionesService } from './calificacionesService'

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

const IMPORT_MOCK = { importadas: 16, actualizadas: 0, omitidas: 0, warnings: [] }
const UMBRAL_MOCK = {
  id: null,
  asignacion_id: null,
  materia_id: MAT,
  umbral_pct: 60,
  valores_aprobatorios: ['Satisfactorio'],
  es_default: true,
}

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('calificacionesService.preview', () => {
  it('llama POST /preview con el archivo y devuelve GradePreview', async () => {
    let called = false
    server.use(
      http.post(`${URL_BASE}/preview`, () => {
        called = true
        return HttpResponse.json(PREVIEW_MOCK)
      }),
    )

    const file = new File(['data'], 'notas.csv', { type: 'text/csv' })
    const result = await calificacionesService.preview(MAT, COH, file)

    expect(called).toBe(true)
    expect(result.actividades).toHaveLength(2)
    expect(result.total_alumnos).toBe(8)
    expect(result.warnings).toEqual([])
  })

  it('mapea correctamente el tipo de actividad', async () => {
    server.use(http.post(`${URL_BASE}/preview`, () => HttpResponse.json(PREVIEW_MOCK)))
    const file = new File(['x'], 'f.csv')
    const result = await calificacionesService.preview(MAT, COH, file)
    expect(result.actividades[0].tipo).toBe('numerica')
    expect(result.actividades[1].tipo).toBe('textual')
  })
})

describe('calificacionesService.importar', () => {
  it('POST /importar con query params actividades_seleccionadas correctos', async () => {
    let capturedParams: string[] = []
    server.use(
      http.post(`${URL_BASE}/importar`, ({ request }) => {
        capturedParams = new URL(request.url).searchParams.getAll('actividades_seleccionadas')
        return HttpResponse.json(IMPORT_MOCK, { status: 201 })
      }),
    )

    const file = new File(['data'], 'notas.xlsx')
    const result = await calificacionesService.importar(MAT, COH, file, [
      'Tarea 1 (Real)',
      'Presentación',
    ])

    expect(capturedParams).toEqual(['Tarea 1 (Real)', 'Presentación'])
    expect(result).toEqual(IMPORT_MOCK)
  })

  it('encode correcto con actividad de nombre especial (paréntesis)', async () => {
    let capturedParams: string[] = []
    server.use(
      http.post(`${URL_BASE}/importar`, ({ request }) => {
        capturedParams = new URL(request.url).searchParams.getAll('actividades_seleccionadas')
        return HttpResponse.json(IMPORT_MOCK, { status: 201 })
      }),
    )

    const file = new File(['x'], 'f.csv')
    await calificacionesService.importar(MAT, COH, file, ['Tarea 1 (Real)'])
    expect(capturedParams).toEqual(['Tarea 1 (Real)'])
  })

  it('usa actividades=[] si no se pasan', async () => {
    let capturedParams: string[] = []
    server.use(
      http.post(`${URL_BASE}/importar`, ({ request }) => {
        capturedParams = new URL(request.url).searchParams.getAll('actividades_seleccionadas')
        return HttpResponse.json(IMPORT_MOCK, { status: 201 })
      }),
    )
    const file = new File(['x'], 'f.csv')
    await calificacionesService.importar(MAT, COH, file, [])
    expect(capturedParams).toEqual([])
  })
})

describe('calificacionesService.getUmbral / putUmbral', () => {
  it('GET /umbral devuelve UmbralMateriaResponse', async () => {
    server.use(
      http.get(`${URL_BASE}/umbral`, () => HttpResponse.json(UMBRAL_MOCK)),
    )
    const result = await calificacionesService.getUmbral(MAT, COH)
    expect(result.umbral_pct).toBe(60)
    expect(result.es_default).toBe(true)
  })

  it('PUT /umbral envía body y devuelve respuesta actualizada', async () => {
    let capturedBody: unknown
    const updated = { ...UMBRAL_MOCK, umbral_pct: 75, es_default: false }
    server.use(
      http.put(`${URL_BASE}/umbral`, async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(updated)
      }),
    )

    const result = await calificacionesService.putUmbral(MAT, COH, {
      umbral_pct: 75,
      valores_aprobatorios: ['Satisfactorio'],
    })

    expect(capturedBody).toEqual({ umbral_pct: 75, valores_aprobatorios: ['Satisfactorio'] })
    expect(result.umbral_pct).toBe(75)
  })
})

describe('calificacionesService.vaciar', () => {
  it('DELETE /vaciar y devuelve VaciarResult', async () => {
    server.use(
      http.delete(`${URL_BASE}/vaciar`, () => HttpResponse.json({ eliminadas: 32 })),
    )
    const result = await calificacionesService.vaciar(MAT, COH)
    expect(result.eliminadas).toBe(32)
  })
})
