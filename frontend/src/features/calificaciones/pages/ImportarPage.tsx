import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { UploadZone } from '../components/UploadZone'
import { ActividadesSelector } from '../components/ActividadesSelector'
import { UmbralForm } from '../components/UmbralForm'
import { calificacionesService } from '../services/calificacionesService'
import type { GradePreview, ImportarCalificacionesResult } from '../types/calificaciones.types'

type Step = 1 | 2 | 3

const ERRORS: Record<string, string> = {
  archivo_invalido: 'El archivo no tiene el formato esperado (.xlsx o .csv)',
  sin_columna_email: 'No se detectó columna de email en el archivo',
  no_hay_padron_activo: 'No hay padrón de alumnos activo para esta materia/cohorte. Importá el padrón primero.',
  actividad_invalida: 'Algunas actividades seleccionadas no están en el archivo',
}

const errMsg = (e: unknown) =>
  ERRORS[(e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? ''] ??
  'Ocurrió un error inesperado'

export function ImportarPage() {
  const { materiaId, cohorteId } = useParams<{ materiaId: string; cohorteId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [step, setStep] = useState<Step>(1)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<GradePreview | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [result, setResult] = useState<ImportarCalificacionesResult | null>(null)
  const [vaciarOpen, setVaciarOpen] = useState(false)

  const previewMut = useMutation({
    mutationFn: (f: File) => calificacionesService.preview(materiaId!, cohorteId!, f),
    onSuccess: (data) => {
      setPreview(data)
      setSelected(data.actividades.map((a) => a.nombre))
      setStep(2)
    },
  })

  const importMut = useMutation({
    mutationFn: () =>
      calificacionesService.importar(materiaId!, cohorteId!, file!, selected),
    onSuccess: (data) => {
      setResult(data)
      qc.invalidateQueries({ queryKey: ['reporte-rapido', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['atrasados', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['ranking', materiaId, cohorteId] })
    },
  })

  const vaciarMut = useMutation({
    mutationFn: () => calificacionesService.vaciar(materiaId!, cohorteId!),
    onSuccess: () => {
      setVaciarOpen(false)
      qc.invalidateQueries({ queryKey: ['reporte-rapido', materiaId, cohorteId] })
    },
  })

  const primary = 'rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 transition bg-blue-600 text-white hover:bg-blue-700'
  const secondary = 'rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 transition bg-gray-100 text-gray-700 hover:bg-gray-200'

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Importar calificaciones</h2>
        <button
          onClick={() => setVaciarOpen(true)}
          className="text-sm text-red-600 hover:underline"
        >
          Vaciar mis calificaciones
        </button>
      </div>

      {/* Step 1 — Upload */}
      {step === 1 && (
        <div className="space-y-4">
          <UploadZone file={file} onFile={setFile} disabled={previewMut.isPending} />
          {previewMut.isError && (
            <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
              {errMsg(previewMut.error)}
            </div>
          )}
          <button
            className={primary}
            disabled={!file || previewMut.isPending}
            onClick={() => file && previewMut.mutate(file)}
          >
            {previewMut.isPending ? 'Analizando…' : 'Analizar archivo →'}
          </button>
        </div>
      )}

      {/* Step 2 — Select + Umbral */}
      {step === 2 && preview && (
        <div className="space-y-6">
          <p className="text-sm text-gray-600">{preview.total_alumnos} alumno(s) detectados</p>
          {preview.warnings.map((w, i) => (
            <div key={i} className="rounded-md bg-yellow-50 p-3 text-sm text-yellow-700">
              {w}
            </div>
          ))}
          <ActividadesSelector
            actividades={preview.actividades}
            selected={selected}
            onChange={setSelected}
          />
          <UmbralForm materiaId={materiaId!} cohorteId={cohorteId!} />
          <div className="flex gap-3">
            <button className={secondary} onClick={() => setStep(1)}>
              ← Volver
            </button>
            <button
              className={primary}
              disabled={selected.length === 0}
              onClick={() => setStep(3)}
            >
              Continuar →
            </button>
          </div>
        </div>
      )}

      {/* Step 3 — Confirm */}
      {step === 3 && !result && (
        <div className="space-y-4">
          <p className="text-sm text-gray-700">
            Vas a importar <strong>{selected.length}</strong> actividad(es) para{' '}
            <strong>{preview?.total_alumnos}</strong> alumno(s).
          </p>
          {importMut.isError && (
            <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
              {errMsg(importMut.error)}
            </div>
          )}
          <div className="flex gap-3">
            <button className={secondary} onClick={() => setStep(2)}>
              ← Volver
            </button>
            <button
              className={primary}
              disabled={importMut.isPending}
              onClick={() => importMut.mutate()}
            >
              {importMut.isPending ? 'Importando…' : 'Importar calificaciones'}
            </button>
          </div>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-4">
          <div className="rounded-md bg-green-50 p-4">
            <p className="font-medium text-green-800">Importación exitosa</p>
            <p className="mt-1 text-sm text-green-700">
              {result.importadas} calificaciones importadas
              {result.actualizadas > 0 && `, ${result.actualizadas} actualizadas`}
              {result.omitidas > 0 && `, ${result.omitidas} omitidas`}
            </p>
          </div>
          <button className={primary} onClick={() => navigate(`/calificaciones/${materiaId}/${cohorteId}/atrasados`)}>
            Ver análisis →
          </button>
        </div>
      )}

      {/* Vaciar dialog */}
      {vaciarOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 flex items-center justify-center bg-black/30"
        >
          <div className="rounded-lg bg-white p-6 shadow-xl">
            <p className="font-medium text-gray-800">¿Vaciar todas las calificaciones?</p>
            <p className="mt-1 text-sm text-gray-500">Esta acción no se puede deshacer.</p>
            <div className="mt-4 flex gap-3">
              <button className={secondary} onClick={() => setVaciarOpen(false)}>
                Cancelar
              </button>
              <button
                className="rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 transition bg-red-600 text-white hover:bg-red-700"
                disabled={vaciarMut.isPending}
                onClick={() => vaciarMut.mutate()}
              >
                {vaciarMut.isPending ? 'Vaciando…' : 'Sí, vaciar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
