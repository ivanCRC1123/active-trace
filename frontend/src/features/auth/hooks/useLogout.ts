import { useCallback } from 'react'
import { logoutApi } from '../services/authService'
import { useSessionStore } from '@/store/sessionStore'

export function useLogout() {
  const clearSession = useSessionStore((s) => s.clearSession)

  return useCallback(async () => {
    try {
      await logoutApi()
    } catch {
      // Server-side revocation failed but the local session must still be cleared.
    } finally {
      clearSession()
      window.location.href = '/login'
    }
  }, [clearSession])
}
