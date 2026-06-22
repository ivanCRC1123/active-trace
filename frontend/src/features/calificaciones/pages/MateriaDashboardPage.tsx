import { NavLink, Outlet, useParams } from 'react-router-dom'

const TABS = [
  { label: 'Importar', path: 'importar' },
  { label: 'Atrasados', path: 'atrasados' },
  { label: 'Ranking', path: 'ranking' },
  { label: 'Notas finales', path: 'notas-finales' },
  { label: 'Sin corregir', path: 'sin-corregir' },
]

export function MateriaDashboardPage() {
  const { materiaId, cohorteId } = useParams<{ materiaId: string; cohorteId: string }>()
  const base = `/calificaciones/${materiaId}/${cohorteId}`

  return (
    <div>
      <nav
        aria-label="Secciones de materia"
        className="mb-6 flex gap-1 border-b border-gray-200"
      >
        {TABS.map((tab) => (
          <NavLink
            key={tab.path}
            to={`${base}/${tab.path}`}
            className={({ isActive }) =>
              `-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-800'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}
