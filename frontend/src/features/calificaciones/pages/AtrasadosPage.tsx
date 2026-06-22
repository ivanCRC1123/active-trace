import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAtrasados } from '../hooks/useAtrasados'
import { usePermission } from '@/shared/hooks/usePermission'
import { AtrasadosTable } from '../components/AtrasadosTable'

export function AtrasadosPage() {
  const { materiaId, cohorteId } = useParams<{ materiaId: string; cohorteId: string }>()
  const { data, isLoading, isError } = useAtrasados(materiaId!, cohorteId!)
  const { granted: canComunicar } = usePermission('comunicacion:enviar')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const navigate = useNavigate()

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (isLoading) return <div className="py-8 text-center text-gray-400">Cargando...</div>
  if (isError) return <div className="py-8 text-center text-red-500">Error al cargar datos.</div>
  if (!data) return null

  if (data.total_alumnos === 0) {
    return (
      <div className="py-12 text-center text-gray-500">
        No hay calificaciones importadas. Importá primero.
      </div>
    )
  }

  if (data.atrasados.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-green-700">
        <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
        <span className="font-medium">Todos los alumnos están al día</span>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-600">
          {data.total_atrasados} alumno(s) atrasados de {data.total_alumnos}
        </p>
        {canComunicar && (
          <button
            disabled={selectedIds.size === 0}
            onClick={() =>
              navigate('/comunicaciones/nuevo', {
                state: {
                  entrada_padron_ids: Array.from(selectedIds),
                  materia_id: materiaId,
                  cohorte_id: cohorteId,
                },
              })
            }
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Enviar comunicación
          </button>
        )}
      </div>
      <AtrasadosTable atrasados={data.atrasados} selectedIds={selectedIds} onToggle={toggle} />
    </div>
  )
}
