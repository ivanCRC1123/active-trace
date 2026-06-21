import { useState, useEffect } from 'react'
import { refreshToken, fetchPermissions, decodeJwt } from '@/features/auth/services/authService'
import { useSessionStore } from '@/store/sessionStore'

export function useBootstrap(): boolean {
  const [bootstrapping, setBootstrapping] = useState(true)
  const setSession = useSessionStore((s) => s.setSession)
  const clearSession = useSessionStore((s) => s.clearSession)

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const token = await refreshToken()
        const user = decodeJwt(token)
        const permissions = await fetchPermissions(token)
        if (!cancelled) {
          setSession(token, user, permissions)
        }
      } catch {
        if (!cancelled) {
          clearSession()
        }
      } finally {
        if (!cancelled) {
          setBootstrapping(false)
        }
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [])

  return bootstrapping
}
