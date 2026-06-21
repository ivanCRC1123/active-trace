import { create } from 'zustand'

interface SessionState {
  accessToken: string | null
  user: null
  permissions: string[]
}

export const useSessionStore = create<SessionState>(() => ({
  accessToken: null,
  user: null,
  permissions: [],
}))
