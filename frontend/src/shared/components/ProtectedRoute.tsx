import { Navigate, Outlet } from 'react-router-dom'
import { useSessionStore } from '@/store/sessionStore'
import { usePermission } from '@/shared/hooks/usePermission'

interface Props {
  requiredPermission?: string
  forbiddenRedirect?: string
}

export function ProtectedRoute({ requiredPermission, forbiddenRedirect = '/403' }: Props) {
  const token = useSessionStore((s) => s.accessToken)
  const { granted } = usePermission(requiredPermission ?? '')

  if (!token) return <Navigate to="/login" replace />
  if (requiredPermission && !granted) return <Navigate to={forbiddenRedirect} replace />

  return <Outlet />
}
