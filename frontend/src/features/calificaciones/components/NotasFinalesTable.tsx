import type { NotaFinalAlumno } from '../types/calificaciones.types'

function notaClass(pct: number | null, umbral: number): string {
  if (pct === null) return 'text-gray-400'
  if (pct >= umbral) return 'text-green-700 font-medium'
  return 'text-red-600 font-medium'
}

interface NotasFinalesTableProps {
  items: NotaFinalAlumno[]
  umbralPct: number
}

export function NotasFinalesTable({ items, umbralPct }: NotasFinalesTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase text-gray-500">
            <th className="py-3 pr-4">Apellidos</th>
            <th className="py-3 pr-4">Nombre</th>
            <th className="py-3 pr-4">Comisión</th>
            <th className="py-3 pr-4">Aprobadas</th>
            <th className="py-3 pr-4">Total</th>
            <th className="py-3">Nota Final</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.entrada_padron_id} className="border-b border-gray-100 hover:bg-gray-50">
              <td className="py-3 pr-4 font-medium">{item.apellidos}</td>
              <td className="py-3 pr-4">{item.nombre}</td>
              <td className="py-3 pr-4">{item.comision ?? '—'}</td>
              <td className="py-3 pr-4">{item.aprobadas}</td>
              <td className="py-3 pr-4">{item.total_calificaciones}</td>
              <td className={`py-3 ${notaClass(item.pct_actividades_aprobadas, umbralPct)}`}>
                {item.pct_actividades_aprobadas !== null
                  ? `${item.pct_actividades_aprobadas.toFixed(2)} %`
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
