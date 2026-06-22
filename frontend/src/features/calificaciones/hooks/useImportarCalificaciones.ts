import { useMutation, useQueryClient } from '@tanstack/react-query'
import { calificacionesService } from '../services/calificacionesService'

interface ImportarArgs {
  file: File
  actividades: string[]
}

export function useImportarCalificaciones(materiaId: string, cohorteId: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({ file, actividades }: ImportarArgs) =>
      calificacionesService.importar(materiaId, cohorteId, file, actividades),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['atrasados', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['ranking', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['notas-finales', materiaId, cohorteId] })
      qc.invalidateQueries({ queryKey: ['reporte-rapido', materiaId, cohorteId] })
    },
  })
}
