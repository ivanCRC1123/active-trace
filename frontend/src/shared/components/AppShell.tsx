import { NavLink, Outlet } from 'react-router-dom'
import { usePermission } from '@/shared/hooks/usePermission'
import { useLogout } from '@/features/auth/hooks/useLogout'

interface MenuItemDef {
  label: string
  path: string
  permission: string | null
}

export const MENU_ITEMS: MenuItemDef[] = [
  { label: 'Inicio', path: '/', permission: null },
  { label: 'Calificaciones', path: '/calificaciones', permission: 'calificaciones:importar' },
  { label: 'Monitor', path: '/monitor', permission: 'atrasados:ver' },
  { label: 'Comunicaciones', path: '/comunicaciones', permission: 'comunicacion:enviar' },
  { label: 'Usuarios', path: '/usuarios', permission: 'usuarios:gestionar' },
  { label: 'Alumnos', path: '/alumnos', permission: 'padron:ver' },
  { label: 'Materias', path: '/materias', permission: 'estructura_academica:gestionar' },
  { label: 'Liquidaciones', path: '/liquidaciones', permission: 'liquidaciones:calcular_cerrar' },
  { label: 'Auditoría', path: '/auditoria', permission: 'auditoria:ver' },
]

function NavItem({ item }: { item: MenuItemDef }) {
  const { granted } = usePermission(item.permission ?? '')
  if (item.permission !== null && !granted) return null
  return (
    <NavLink
      to={item.path}
      end={item.path === '/'}
      className={({ isActive }) =>
        `block px-4 py-2 rounded text-sm ${
          isActive ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-100'
        }`
      }
    >
      {item.label}
    </NavLink>
  )
}

export function AppShell() {
  const logout = useLogout()

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <span className="font-semibold text-gray-800">trace</span>
        <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-700">
          Salir
        </button>
      </header>
      <div className="flex flex-1">
        <nav
          aria-label="Menú principal"
          className="w-56 border-r border-gray-200 p-4 flex flex-col gap-1"
        >
          {MENU_ITEMS.map((item) => (
            <NavItem key={item.path} item={item} />
          ))}
        </nav>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
