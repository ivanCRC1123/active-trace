import { useState } from 'react'
import type { LoginPhase } from '../types'
import {
  loginWithCredentials,
  verifyTwoFA,
  fetchPermissions,
  decodeJwt,
} from '../services/authService'
import { useSessionStore } from '@/store/sessionStore'

interface MachineState {
  phase: LoginPhase
  sessionToken: string | null
  error: string | null
  loading: boolean
}

const INITIAL: MachineState = { phase: 'IDLE', sessionToken: null, error: null, loading: false }

export function useLoginMachine() {
  const [state, setState] = useState<MachineState>(INITIAL)
  const setSession = useSessionStore((s) => s.setSession)

  async function submitCredentials(email: string, password: string) {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const result = await loginWithCredentials(email, password)
      if ('requires_2fa' in result) {
        setState({ phase: 'AWAITING_2FA', sessionToken: result.session_token, error: null, loading: false })
      } else {
        const user = decodeJwt(result.access_token)
        const permissions = await fetchPermissions(result.access_token)
        setSession(result.access_token, user, permissions)
        setState({ phase: 'AUTHENTICATED', sessionToken: null, error: null, loading: false })
      }
    } catch {
      setState((s) => ({ ...s, loading: false, error: 'Credenciales incorrectas. Verificá e intentá de nuevo.' }))
    }
  }

  async function submitTwoFA(code: string) {
    if (!state.sessionToken) return
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const result = await verifyTwoFA(state.sessionToken, code)
      const user = decodeJwt(result.access_token)
      const permissions = await fetchPermissions(result.access_token)
      setSession(result.access_token, user, permissions)
      setState({ phase: 'AUTHENTICATED', sessionToken: null, error: null, loading: false })
    } catch {
      setState((s) => ({ ...s, loading: false, error: 'Código incorrecto. Verificá e intentá de nuevo.' }))
    }
  }

  return { state, submitCredentials, submitTwoFA }
}
