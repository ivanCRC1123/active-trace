import { create } from 'zustand'

export interface User {
  user_id: string
  tenant_id: string
  roles: string[]
  impersonado_id?: string | null
}

// permissions: mapa de /me/permissions — { 'usuarios:leer': 'all', 'tareas:crear': 'own' }
interface SessionState {
  accessToken: string | null
  user: User | null
  permissions: Record<string, string>
}

interface SessionActions {
  setSession: (accessToken: string, user: User, permissions: Record<string, string>) => void
  updateAccessToken: (accessToken: string) => void
  clearSession: () => void
}

export const useSessionStore = create<SessionState & SessionActions>((set) => ({
  accessToken: null,
  user: null,
  permissions: {},
  setSession: (accessToken, user, permissions) => set({ accessToken, user, permissions }),
  updateAccessToken: (accessToken) => set({ accessToken }),
  clearSession: () => set({ accessToken: null, user: null, permissions: {} }),
}))
