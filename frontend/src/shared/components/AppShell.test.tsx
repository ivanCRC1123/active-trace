import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppShell } from './AppShell'
import { useSessionStore } from '@/store/sessionStore'

afterEach(() => {
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
})

function renderShell(permissions: Record<string, string> = {}) {
  useSessionStore.setState({
    accessToken: 'tok',
    user: { user_id: 'u1', tenant_id: 't1', roles: [] },
    permissions,
  })
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<div data-testid="content">Dashboard</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppShell menu filtering', () => {
  it('always shows Inicio to authenticated users regardless of permissions', () => {
    renderShell({})
    expect(screen.getByRole('link', { name: 'Inicio' })).toBeInTheDocument()
  })

  it('shows Usuarios link when user has usuarios:leer permission', () => {
    renderShell({ 'usuarios:leer': 'all' })
    expect(screen.getByRole('link', { name: 'Usuarios' })).toBeInTheDocument()
  })

  it('hides Usuarios link when user lacks usuarios:leer permission', () => {
    renderShell({})
    expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument()
  })

  it('shows Alumnos link when user has alumnos:leer permission', () => {
    renderShell({ 'alumnos:leer': 'own' })
    expect(screen.getByRole('link', { name: 'Alumnos' })).toBeInTheDocument()
  })

  it('hides Alumnos link when user lacks alumnos:leer permission', () => {
    renderShell({})
    expect(screen.queryByRole('link', { name: 'Alumnos' })).not.toBeInTheDocument()
  })

  it('shows only permitted items when user has a subset of permissions', () => {
    renderShell({ 'usuarios:leer': 'all', 'materias:leer': 'all' })
    expect(screen.getByRole('link', { name: 'Usuarios' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Materias' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Alumnos' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Liquidaciones' })).not.toBeInTheDocument()
  })

  it('renders the outlet content', () => {
    renderShell({})
    expect(screen.getByTestId('content')).toBeInTheDocument()
  })

  it('renders header with app name', () => {
    renderShell({})
    expect(screen.getByText('trace')).toBeInTheDocument()
  })
})
