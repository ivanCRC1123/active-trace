import type { ActivityInfo } from '../types/calificaciones.types'

interface Props {
  actividades: ActivityInfo[]
  selected: string[]
  onChange: (selected: string[]) => void
}

export function ActividadesSelector({ actividades, selected, onChange }: Props) {
  const toggle = (nombre: string) => {
    onChange(
      selected.includes(nombre)
        ? selected.filter((n) => n !== nombre)
        : [...selected, nombre],
    )
  }

  return (
    <ul aria-label="actividades detectadas" className="space-y-2">
      {actividades.map((act) => (
        <li
          key={act.nombre}
          className="flex items-center gap-3 rounded-md border border-gray-100 px-3 py-2"
        >
          <input
            type="checkbox"
            id={`act-${act.nombre}`}
            checked={selected.includes(act.nombre)}
            onChange={() => toggle(act.nombre)}
            className="h-4 w-4 rounded border-gray-300 text-blue-600"
          />
          <label
            htmlFor={`act-${act.nombre}`}
            className="flex-1 cursor-pointer text-sm text-gray-800"
          >
            {act.nombre}
          </label>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              act.tipo === 'numerica'
                ? 'bg-blue-100 text-blue-700'
                : 'bg-purple-100 text-purple-700'
            }`}
          >
            {act.tipo}
          </span>
        </li>
      ))}
    </ul>
  )
}
