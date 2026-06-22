import { Link } from 'react-router-dom'
import { useMeAsignaciones } from '../hooks/useMeAsignaciones'

export function CalificacionesHomePage() {
  const { data, isLoading, isError } = useMeAsignaciones()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500">
        Cargando materias…
      </div>
    )
  }

  if (isError) {
    return <p className="py-8 text-red-600">No se pudieron cargar las materias.</p>
  }

  const items = (data ?? []).filter((a) => a.materia_id !== null && a.cohorte_id !== null)

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-lg font-medium text-gray-700">Sin materias asignadas</p>
        <p className="mt-2 text-sm text-gray-500">
          No tenés materias asignadas con calificaciones disponibles.
        </p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-800">Calificaciones</h1>
      <ul className="space-y-3">
        {items.map((asig) => (
          <li key={asig.id}>
            <Link
              to={`/calificaciones/${asig.materia_id}/${asig.cohorte_id}`}
              className="block rounded-lg border border-gray-200 bg-white px-5 py-4 shadow-sm transition hover:border-blue-400 hover:shadow-md"
            >
              <p className="font-medium text-gray-800">
                {asig.materia_nombre ?? 'Materia sin nombre'}
              </p>
              <p className="mt-1 text-sm text-gray-500">
                {asig.carrera_nombre && <span>{asig.carrera_nombre} · </span>}
                {asig.cohorte_nombre ?? 'Cohorte sin nombre'}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
