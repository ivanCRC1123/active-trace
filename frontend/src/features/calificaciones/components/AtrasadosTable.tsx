import type { AlumnoAtrasado } from '../types/calificaciones.types'

function ChipList({ items, colorClass }: { items: string[]; colorClass: string }) {
  const visible = items.slice(0, 3)
  const extra = items.length - 3
  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((item) => (
        <span key={item} className={`rounded px-1.5 py-0.5 text-xs font-medium ${colorClass}`}>
          {item}
        </span>
      ))}
      {extra > 0 && (
        <span className="rounded px-1.5 py-0.5 text-xs text-gray-500">+{extra} más</span>
      )}
    </div>
  )
}

interface AtrasadosTableProps {
  atrasados: AlumnoAtrasado[]
  selectedIds: Set<string>
  onToggle: (id: string) => void
}

export function AtrasadosTable({ atrasados, selectedIds, onToggle }: AtrasadosTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase text-gray-500">
            <th className="py-3 pr-4">Apellidos</th>
            <th className="py-3 pr-4">Nombre</th>
            <th className="py-3 pr-4">Comisión</th>
            <th className="py-3 pr-4">Regional</th>
            <th className="py-3 pr-4">Act. Faltantes</th>
            <th className="py-3 pr-4">Bajo Umbral</th>
            <th className="py-3 text-center">Sel.</th>
          </tr>
        </thead>
        <tbody>
          {atrasados.map((a) => (
            <tr key={a.entrada_padron_id} className="border-b border-gray-100 hover:bg-gray-50">
              <td className="py-3 pr-4 font-medium">{a.apellidos}</td>
              <td className="py-3 pr-4">{a.nombre}</td>
              <td className="py-3 pr-4">{a.comision ?? '—'}</td>
              <td className="py-3 pr-4">{a.regional ?? '—'}</td>
              <td className="py-3 pr-4">
                {a.actividades_faltantes.length > 0 ? (
                  <ChipList
                    items={a.actividades_faltantes}
                    colorClass="bg-yellow-100 text-yellow-800"
                  />
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
              <td className="py-3 pr-4">
                {a.actividades_bajo_umbral.length > 0 ? (
                  <ChipList
                    items={a.actividades_bajo_umbral}
                    colorClass="bg-red-100 text-red-800"
                  />
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
              <td className="py-3 text-center">
                <input
                  type="checkbox"
                  aria-label={`Seleccionar ${a.apellidos} ${a.nombre}`}
                  checked={selectedIds.has(a.entrada_padron_id)}
                  onChange={() => onToggle(a.entrada_padron_id)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
