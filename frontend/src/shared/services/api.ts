import axios from 'axios'
import type { InternalAxiosRequestConfig } from 'axios'
import { useSessionStore } from '@/store/sessionStore'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  withCredentials: true,
})

// Single-flight refresh: shared promise while a refresh is in-flight.
// N concurrent 401s → only one POST /auth/refresh; all N wait on this same promise.
let refreshPromise: Promise<string> | null = null

api.interceptors.request.use((config) => {
  const token = useSessionStore.getState().accessToken
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    // 403 is an authorization problem, not an expired token — never refresh.
    if (error.response?.status === 403) {
      return Promise.reject(error)
    }

    if (error.response?.status === 401) {
      // Loop prevention — bail out immediately in two situations:
      //   1. This 401 is from /auth/refresh itself (the token is truly dead).
      //   2. We already retried this request once (avoid infinite retry loops).
      const isRefreshCall = config.url?.endsWith('/auth/refresh') ?? false
      if (isRefreshCall || config._retry) {
        useSessionStore.getState().clearSession()
        // Only redirect if not already on /login — prevents infinite reload loop
        // when bootstrap's own /auth/refresh fails while the user is at /login.
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }

      // If there is no active session token there is nothing to refresh.
      if (!useSessionStore.getState().accessToken) {
        return Promise.reject(error)
      }

      config._retry = true

      try {
        // Single-flight: if no refresh is already in-flight, start one.
        // Concurrent callers reuse the existing promise rather than
        // sending a second POST /auth/refresh. The backend rotates the
        // refresh token on every call — two concurrent refreshes would
        // mutually revoke each other → logout. The single-flight prevents that.
        if (!refreshPromise) {
          refreshPromise = api
            .post<{ access_token: string }>('/auth/refresh')
            .then((res) => {
              const newToken = res.data.access_token
              useSessionStore.getState().updateAccessToken(newToken)
              return newToken
            })
            .finally(() => {
              refreshPromise = null
            })
        }

        const newToken = await refreshPromise
        config.headers['Authorization'] = `Bearer ${newToken}`
        return api(config)
      } catch {
        useSessionStore.getState().clearSession()
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  },
)
