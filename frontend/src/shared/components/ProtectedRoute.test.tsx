import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { ProtectedRoute } from './ProtectedRoute'
import { useSessionStore } from '@/store/sessionStore'

afterEach(() => {
  useSessionStore.setState({ accessToken: null, user: null, permissions: {} })
})

function renderWith(initialPath: string, requiredPermission?: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div data-testid="login">Login</div>} />
        <Route path="/403" element={<div data-testid="forbidden">Forbidden</div>} />
        <Route element={<ProtectedRoute requiredPermission={requiredPermission} />}>
          <Route path="/" element={<div data-testid="protected">Protected</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('redirects to /login when there is no session', () => {
    renderWith('/')
    expect(screen.getByTestId('login')).toBeInTheDocument()
    expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
  })

  it('renders outlet when session exists and no permission is required', () => {
    useSessionStore.setState({ accessToken: 'tok', user: null, permissions: {} })
    renderWith('/')
    expect(screen.getByTestId('protected')).toBeInTheDocument()
  })

  it('redirects to /403 when session exists but required permission is missing', () => {
    useSessionStore.setState({ accessToken: 'tok', user: null, permissions: {} })
    renderWith('/', 'usuarios:leer')
    expect(screen.getByTestId('forbidden')).toBeInTheDocument()
    expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
  })

  it('renders outlet when session exists and required permission is present', () => {
    useSessionStore.setState({
      accessToken: 'tok',
      user: null,
      permissions: { 'usuarios:leer': 'all' },
    })
    renderWith('/', 'usuarios:leer')
    expect(screen.getByTestId('protected')).toBeInTheDocument()
  })
})
