import { useEffect, useState } from 'react'
import { useUmbral } from '../hooks/useUmbral'

interface Props {
  materiaId: string
  cohorteId: string
}

export function UmbralForm({ materiaId, cohorteId }: Props) {
  const { data, update } = useUmbral(materiaId, cohorteId)
  const [pct, setPct] = useState(60)
  const [valoresText, setValoresText] = useState('Satisfactorio, Supera lo esperado')

  useEffect(() => {
    if (data) {
      setPct(data.umbral_pct)
      setValoresText(data.valores_aprobatorios.join(', '))
    }
  }, [data])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const valores = valoresText
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean)
    update.mutate({ umbral_pct: pct, valores_aprobatorios: valores })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-md border border-gray-200 p-4">
      <p className="text-sm font-medium text-gray-700">Configuración de umbral (opcional)</p>
      <div>
        <label className="block text-sm text-gray-600">
          Umbral de aprobación: <span className="font-semibold">{pct}%</span>
        </label>
        <input
          type="range"
          min={1}
          max={100}
          value={pct}
          onChange={(e) => setPct(Number(e.target.value))}
          aria-label="umbral de aprobación"
          className="mt-1 w-full"
        />
      </div>
      <div>
        <label htmlFor="valores-aprobatorios" className="block text-sm text-gray-600">
          Valores aprobatorios (separados por coma)
        </label>
        <input
          id="valores-aprobatorios"
          type="text"
          value={valoresText}
          onChange={(e) => setValoresText(e.target.value)}
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={update.isPending}
        className="rounded-md bg-gray-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
      >
        {update.isPending ? 'Guardando…' : 'Guardar umbral'}
      </button>
      {update.isSuccess && (
        <p className="text-xs text-green-600">Umbral guardado</p>
      )}
    </form>
  )
}
