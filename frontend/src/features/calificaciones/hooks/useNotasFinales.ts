import { useQuery } from '@tanstack/react-query'
import { calificacionesService } from '../services/calificacionesService'

export function useNotasFinales(materiaId: string, cohorteId: string) {
  return useQuery({
    queryKey: ['notas-finales', materiaId, cohorteId],
    queryFn: () => calificacionesService.getNotasFinales(materiaId, cohorteId),
  })
}
