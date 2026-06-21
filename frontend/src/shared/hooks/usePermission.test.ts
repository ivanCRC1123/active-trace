import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { usePermission } from './usePermission'
import { useSessionStore } from '@/store/sessionStore'

afterEach(() => {
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
})

describe('usePermission', () => {
  it('returns granted=true and scope=all when permission is present with all scope', () => {
    useSessionStore.setState({ permissions: { 'usuarios:leer': 'all' } })
    const { result } = renderHook(() => usePermission('usuarios:leer'))
    expect(result.current.granted).toBe(true)
    expect(result.current.scope).toBe('all')
  })

  it('returns granted=true and scope=own when permission is present with own scope', () => {
    useSessionStore.setState({ permissions: { 'tareas:crear': 'own' } })
    const { result } = renderHook(() => usePermission('tareas:crear'))
    expect(result.current.granted).toBe(true)
    expect(result.current.scope).toBe('own')
  })

  it('returns granted=false and scope=null when permission is absent', () => {
    useSessionStore.setState({ permissions: {} })
    const { result } = renderHook(() => usePermission('usuarios:leer'))
    expect(result.current.granted).toBe(false)
    expect(result.current.scope).toBeNull()
  })

  it('returns granted=false for an unrelated permission even when others exist', () => {
    useSessionStore.setState({ permissions: { 'alumnos:leer': 'all' } })
    const { result } = renderHook(() => usePermission('usuarios:leer'))
    expect(result.current.granted).toBe(false)
  })
})
