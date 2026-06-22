import { useParams } from 'react-router-dom'
import { useNotasFinales } from '../hooks/useNotasFinales'
import { useUmbral } from '../hooks/useUmbral'
import { NotasFinalesTable } from '../components/NotasFinalesTable'
import { calificacionesService } from '../services/calificacionesService'

export function NotasFinalesPage() {
  const { materiaId, cohorteId } = useParams<{ materiaId: string; cohorteId: string }>()
  const { data, isLoading, isError } = useNotasFinales(materiaId!, cohorteId!)
  const { data: umbral } = useUmbral(materiaId!, cohorteId!)

  async function handleExport() {
    const blob = await calificacionesService.exportarNotasFinales(materiaId!, cohorteId!)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `notas-finales-${materiaId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading) return <div className="py-8 text-center text-gray-400">Cargando...</div>
  if (isError) return <div className="py-8 text-center text-red-500">Error al cargar datos.</div>
  if (!data) return null

  if (data.items.length === 0) {
    return (
      <div className="py-12 text-center text-gray-500">
        No hay notas finales disponibles. Importá calificaciones primero.
      </div>
    )
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-600">{data.total_alumnos} alumno(s)</p>
        <button
          onClick={handleExport}
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Exportar CSV
        </button>
      </div>
      <NotasFinalesTable items={data.items} umbralPct={umbral?.umbral_pct ?? 60} />
    </div>
  )
}
