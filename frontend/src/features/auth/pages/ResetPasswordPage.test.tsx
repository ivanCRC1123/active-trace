import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ResetPasswordPage } from './ResetPasswordPage'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage(token = 'valid-token') {
  return render(
    <MemoryRouter initialEntries={[`/reset-password?token=${token}`]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ResetPasswordPage', () => {
  it('renders form with password fields', () => {
    renderPage()
    expect(screen.getByLabelText('Nueva contraseña')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirmar contraseña')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar contraseña' })).toBeInTheDocument()
  })

  it('shows error when passwords do not match', async () => {
    renderPage()
    await userEvent.type(screen.getByLabelText('Nueva contraseña'), 'securePass1')
    await userEvent.type(screen.getByLabelText('Confirmar contraseña'), 'differentPass')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    await waitFor(() =>
      expect(screen.getByText('Las contraseñas no coinciden')).toBeInTheDocument(),
    )
  })

  it('shows error for password shorter than 8 characters', async () => {
    renderPage()
    await userEvent.type(screen.getByLabelText('Nueva contraseña'), 'short')
    await userEvent.type(screen.getByLabelText('Confirmar contraseña'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    await waitFor(() =>
      expect(
        screen.getByText('La contraseña debe tener al menos 8 caracteres'),
      ).toBeInTheDocument(),
    )
  })

  it('calls reset endpoint with token from URL query param and redirects to /login on success', async () => {
    server.use(
      http.post(`${BASE}/auth/reset`, async ({ request }) => {
        const body = await request.json() as { token: string; new_password: string }
        expect(body.token).toBe('my-reset-token')
        expect(body.new_password).toBe('newSecure123')
        return HttpResponse.json({ detail: 'Password has been reset successfully.' })
      }),
    )

    renderPage('my-reset-token')
    await userEvent.type(screen.getByLabelText('Nueva contraseña'), 'newSecure123')
    await userEvent.type(screen.getByLabelText('Confirmar contraseña'), 'newSecure123')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    await waitFor(() =>
      expect(screen.getByTestId('login-page')).toBeInTheDocument(),
    )
  })

  it('shows error message when reset token is invalid or expired', async () => {
    server.use(
      http.post(`${BASE}/auth/reset`, () =>
        HttpResponse.json({ detail: 'Invalid token' }, { status: 401 }),
      ),
    )

    renderPage('expired-token')
    await userEvent.type(screen.getByLabelText('Nueva contraseña'), 'newSecure123')
    await userEvent.type(screen.getByLabelText('Confirmar contraseña'), 'newSecure123')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'El token es inválido o ya expiró.',
      ),
    )
  })
})
