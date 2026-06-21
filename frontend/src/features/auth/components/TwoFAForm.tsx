import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const schema = z.object({
  code: z.string().regex(/^\d{6}$/, 'Ingresá los 6 dígitos del código'),
})

type FormValues = z.infer<typeof schema>

interface Props {
  onSubmit: (code: string) => void
  loading: boolean
  error: string | null
}

export function TwoFAForm({ onSubmit, loading, error }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  return (
    <form onSubmit={handleSubmit((v) => onSubmit(v.code))} noValidate>
      <p className="text-sm text-gray-600 mb-4">
        Ingresá el código de 6 dígitos de tu aplicación de autenticación.
      </p>

      <div className="mb-6">
        <label htmlFor="code" className="block text-sm font-medium text-gray-700 mb-1">
          Código de verificación
        </label>
        <input
          id="code"
          type="text"
          inputMode="numeric"
          maxLength={6}
          autoComplete="one-time-code"
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-center tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500"
          {...register('code')}
        />
        {errors.code && (
          <p className="text-red-600 text-xs mt-1">{errors.code.message}</p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-red-600 text-sm mb-4">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full bg-blue-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Verificando...' : 'Verificar'}
      </button>
    </form>
  )
}
