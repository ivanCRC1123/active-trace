interface Props {
  file: File | null
  onFile: (file: File) => void
  disabled?: boolean
}

const ACCEPTED_EXTS = ['.xlsx', '.csv']

export function UploadZone({ file, onFile, disabled }: Props) {
  const accept = (f: File) => {
    const ok = ACCEPTED_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
    if (ok) onFile(f)
  }

  return (
    <div
      data-testid="drop-zone"
      onDrop={(e) => {
        e.preventDefault()
        const f = e.dataTransfer.files[0]
        if (f) accept(f)
      }}
      onDragOver={(e) => e.preventDefault()}
      className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 p-10 text-center transition hover:border-blue-400"
    >
      <input
        data-testid="file-input"
        type="file"
        accept=".xlsx,.csv"
        disabled={disabled}
        className="hidden"
        id="file-upload-input"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) accept(f)
        }}
      />
      <label htmlFor="file-upload-input" className="cursor-pointer space-y-1">
        {file ? (
          <p className="font-medium text-blue-600">{file.name}</p>
        ) : (
          <>
            <p className="text-sm text-gray-600">
              Arrastrá el archivo o{' '}
              <span className="text-blue-600 underline">seleccioná</span>
            </p>
            <p className="text-xs text-gray-400">.xlsx o .csv</p>
          </>
        )}
      </label>
    </div>
  )
}
