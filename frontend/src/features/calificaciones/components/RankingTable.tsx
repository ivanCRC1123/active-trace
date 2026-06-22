import type { RankingItem } from '../types/calificaciones.types'

const POSITION_CLASSES: Record<number, string> = {
  1: 'bg-yellow-100 text-yellow-800',
  2: 'bg-gray-200 text-gray-700',
  3: 'bg-orange-100 text-orange-700',
}

function pct(aprobadas: number, total: number): string {
  if (total === 0) return '0.0%'
  return `${((aprobadas / total) * 100).toFixed(1)}%`
}

interface RankingTableProps {
  items: RankingItem[]
  totalIncluidos: number
  totalExcluidos: number
}

export function RankingTable({ items, totalIncluidos, totalExcluidos }: RankingTableProps) {
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase text-gray-500">
              <th className="py-3 pr-4">#</th>
              <th className="py-3 pr-4">Apellidos</th>
              <th className="py-3 pr-4">Nombre</th>
              <th className="py-3 pr-4">Comisión</th>
              <th className="py-3 pr-4">Aprobadas</th>
              <th className="py-3 pr-4">Total</th>
              <th className="py-3">Porcentaje</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.entrada_padron_id}
                className="border-b border-gray-100 hover:bg-gray-50"
              >
                <td className="py-3 pr-4">
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      POSITION_CLASSES[item.posicion] ?? 'bg-white text-gray-700'
                    }`}
                  >
                    {item.posicion}
                  </span>
                </td>
                <td className="py-3 pr-4 font-medium">{item.apellidos}</td>
                <td className="py-3 pr-4">{item.nombre}</td>
                <td className="py-3 pr-4">{item.comision ?? '—'}</td>
                <td className="py-3 pr-4">{item.total_aprobadas}</td>
                <td className="py-3 pr-4">{item.total_calificaciones}</td>
                <td className="py-3">{pct(item.total_aprobadas, item.total_calificaciones)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-gray-500">
        {totalIncluidos} alumnos incluidos ({totalExcluidos} excluidos sin ninguna aprobada)
      </p>
    </div>
  )
}
