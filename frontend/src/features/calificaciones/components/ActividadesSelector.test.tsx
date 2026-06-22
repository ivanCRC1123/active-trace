import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ActividadesSelector } from './ActividadesSelector'
import type { ActivityInfo } from '../types/calificaciones.types'

const ACTIVIDADES: ActivityInfo[] = [
  { nombre: 'Tarea 1 (Real)', tipo: 'numerica' },
  { nombre: 'Presentación', tipo: 'textual' },
  { nombre: 'Examen (Real)', tipo: 'numerica' },
]

describe('ActividadesSelector', () => {
  it('renderiza todas las actividades', () => {
    render(
      <ActividadesSelector
        actividades={ACTIVIDADES}
        selected={ACTIVIDADES.map((a) => a.nombre)}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('Tarea 1 (Real)')).toBeInTheDocument()
    expect(screen.getByLabelText('Presentación')).toBeInTheDocument()
    expect(screen.getByLabelText('Examen (Real)')).toBeInTheDocument()
  })

  it('todas marcadas por defecto cuando selected incluye todas', () => {
    render(
      <ActividadesSelector
        actividades={ACTIVIDADES}
        selected={ACTIVIDADES.map((a) => a.nombre)}
        onChange={vi.fn()}
      />,
    )
    const checkboxes = screen.getAllByRole('checkbox')
    checkboxes.forEach((cb) => expect(cb).toBeChecked())
  })

  it('muestra badge de tipo para cada actividad', () => {
    render(
      <ActividadesSelector
        actividades={ACTIVIDADES}
        selected={[]}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getAllByText('numerica')).toHaveLength(2)
    expect(screen.getByText('textual')).toBeInTheDocument()
  })

  it('deseleccionar una actividad llama onChange sin ella', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    const allSelected = ACTIVIDADES.map((a) => a.nombre)

    render(
      <ActividadesSelector
        actividades={ACTIVIDADES}
        selected={allSelected}
        onChange={onChange}
      />,
    )

    await user.click(screen.getByLabelText('Presentación'))
    expect(onChange).toHaveBeenCalledWith(['Tarea 1 (Real)', 'Examen (Real)'])
  })

  it('seleccionar una desmarcada llama onChange con ella agregada', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(
      <ActividadesSelector
        actividades={ACTIVIDADES}
        selected={['Tarea 1 (Real)']}
        onChange={onChange}
      />,
    )

    await user.click(screen.getByLabelText('Presentación'))
    expect(onChange).toHaveBeenCalledWith(['Tarea 1 (Real)', 'Presentación'])
  })
})
