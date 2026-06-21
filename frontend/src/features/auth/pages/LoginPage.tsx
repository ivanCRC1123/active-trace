import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLoginMachine } from '../hooks/useLoginMachine'
import { CredentialsForm } from '../components/CredentialsForm'
import { TwoFAForm } from '../components/TwoFAForm'

export function LoginPage() {
  const { state, submitCredentials, submitTwoFA } = useLoginMachine()
  const navigate = useNavigate()

  useEffect(() => {
    if (state.phase === 'AUTHENTICATED') {
      navigate('/', { replace: true })
    }
  }, [state.phase, navigate])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm bg-white rounded-lg shadow-md p-8">
        <h1 className="text-2xl font-bold text-center text-gray-900 mb-6">
          {state.phase === 'AWAITING_2FA' ? 'Verificación en dos pasos' : 'Iniciar sesión'}
        </h1>

        {state.phase === 'AWAITING_2FA' ? (
          <TwoFAForm
            onSubmit={submitTwoFA}
            loading={state.loading}
            error={state.error}
          />
        ) : (
          <CredentialsForm
            onSubmit={submitCredentials}
            loading={state.loading}
            error={state.error}
          />
        )}
      </div>
    </div>
  )
}
