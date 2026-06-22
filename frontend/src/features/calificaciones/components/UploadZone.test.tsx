import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UploadZone } from './UploadZone'

function xlsx(name = 'notas.xlsx') {
  return new File(['data'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

function csv(name = 'notas.csv') {
  return new File(['data'], name, { type: 'text/csv' })
}

describe('UploadZone', () => {
  it('renderiza texto inicial sin archivo', () => {
    render(<UploadZone file={null} onFile={vi.fn()} />)
    expect(screen.getByText(/Arrastrá el archivo/i)).toBeInTheDocument()
    expect(screen.getByText('.xlsx o .csv')).toBeInTheDocument()
  })

  it('muestra el nombre del archivo cuando hay uno seleccionado', () => {
    render(<UploadZone file={xlsx()} onFile={vi.fn()} />)
    expect(screen.getByText('notas.xlsx')).toBeInTheDocument()
  })

  it('acepta .xlsx y llama onFile', async () => {
    const onFile = vi.fn()
    const user = userEvent.setup()
    render(<UploadZone file={null} onFile={onFile} />)
    const input = screen.getByTestId('file-input')
    await user.upload(input, xlsx())
    expect(onFile).toHaveBeenCalledWith(expect.objectContaining({ name: 'notas.xlsx' }))
  })

  it('acepta .csv y llama onFile', async () => {
    const onFile = vi.fn()
    const user = userEvent.setup()
    render(<UploadZone file={null} onFile={onFile} />)
    await user.upload(screen.getByTestId('file-input'), csv())
    expect(onFile).toHaveBeenCalledOnce()
  })

  it('rechaza .pdf y NO llama onFile', async () => {
    const onFile = vi.fn()
    const user = userEvent.setup()
    render(<UploadZone file={null} onFile={onFile} />)
    const pdf = new File(['x'], 'doc.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByTestId('file-input'), pdf)
    expect(onFile).not.toHaveBeenCalled()
  })

  it('acepta drag & drop de .xlsx y llama onFile', () => {
    const onFile = vi.fn()
    render(<UploadZone file={null} onFile={onFile} />)
    const zone = screen.getByTestId('drop-zone')
    const file = xlsx('drag.xlsx')
    fireEvent.drop(zone, { dataTransfer: { files: [file] } })
    expect(onFile).toHaveBeenCalledWith(expect.objectContaining({ name: 'drag.xlsx' }))
  })

  it('rechaza drag & drop de .pdf', () => {
    const onFile = vi.fn()
    render(<UploadZone file={null} onFile={onFile} />)
    const zone = screen.getByTestId('drop-zone')
    const pdf = new File(['x'], 'doc.pdf', { type: 'application/pdf' })
    fireEvent.drop(zone, { dataTransfer: { files: [pdf] } })
    expect(onFile).not.toHaveBeenCalled()
  })
})
