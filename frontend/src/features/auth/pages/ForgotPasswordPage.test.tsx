import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ForgotPasswordPage } from './ForgotPasswordPage'
import { api } from '@/shared/services/api'

const BASE = 'http://localhost/api'
api.defaults.baseURL = BASE

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/forgot-password']}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ForgotPasswordPage', () => {
  it('renders form with email field and submit button', () => {
    renderPage()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Enviar link de recuperación' }),
    ).toBeInTheDocument()
  })

  it('calls the forgot endpoint and shows generic success message', async () => {
    server.use(
      http.post(`${BASE}/auth/forgot`, () =>
        HttpResponse.json({
          detail: 'If the email exists, a recovery token has been generated.',
          recovery_token: null,
        }),
      ),
    )

    renderPage()
    await userEvent.type(screen.getByLabelText('Email'), 'someone@test.com')
    await userEvent.click(
      screen.getByRole('button', { name: 'Enviar link de recuperación' }),
    )

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'Si el email existe, te enviamos un link de recuperación.',
      ),
    )
    // Form is replaced — no submit button visible
    expect(
      screen.queryByRole('button', { name: 'Enviar link de recuperación' }),
    ).not.toBeInTheDocument()
  })

  it('shows the same generic message even when email does not exist (anti-enumeration)', async () => {
    server.use(
      http.post(`${BASE}/auth/forgot`, () =>
        HttpResponse.json({
          detail: 'If the email exists, a recovery token has been generated.',
          recovery_token: null,
        }),
      ),
    )

    renderPage()
    await userEvent.type(screen.getByLabelText('Email'), 'nonexistent@test.com')
    await userEvent.click(
      screen.getByRole('button', { name: 'Enviar link de recuperación' }),
    )

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'Si el email existe, te enviamos un link de recuperación.',
      ),
    )
  })

  it('shows validation error for invalid email without calling the endpoint', async () => {
    renderPage()
    await userEvent.type(screen.getByLabelText('Email'), 'not-an-email')
    await userEvent.click(
      screen.getByRole('button', { name: 'Enviar link de recuperación' }),
    )

    await waitFor(() =>
      expect(screen.getByText('Email inválido')).toBeInTheDocument(),
    )
    // No network call — success state not shown
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
