import { useParams } from 'react-router-dom'
import { useRanking } from '../hooks/useRanking'
import { RankingTable } from '../components/RankingTable'

export function RankingPage() {
  const { materiaId, cohorteId } = useParams<{ materiaId: string; cohorteId: string }>()
  const { data, isLoading, isError } = useRanking(materiaId!, cohorteId!)

  if (isLoading) return <div className="py-8 text-center text-gray-400">Cargando...</div>
  if (isError) return <div className="py-8 text-center text-red-500">Error al cargar datos.</div>
  if (!data) return null

  if (data.items.length === 0) {
    return (
      <div className="py-12 text-center text-gray-500">
        No hay ranking disponible. Importá calificaciones primero.
      </div>
    )
  }

  return (
    <RankingTable
      items={data.items}
      totalIncluidos={data.total_incluidos}
      totalExcluidos={data.total_excluidos}
    />
  )
}
