import { useSessionStore } from '@/store/sessionStore'

export type PermissionScope = 'all' | 'own'

export function usePermission(codigo: string): { granted: boolean; scope: PermissionScope | null } {
  const permissions = useSessionStore((s) => s.permissions)
  const raw = permissions[codigo]
  const scope = raw === 'all' || raw === 'own' ? raw : null
  return { granted: raw !== undefined, scope }
}
