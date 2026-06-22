import { useQuery } from '@tanstack/react-query'
import { calificacionesService } from '../services/calificacionesService'

export function useAtrasados(materiaId: string, cohorteId: string) {
  return useQuery({
    queryKey: ['atrasados', materiaId, cohorteId],
    queryFn: () => calificacionesService.getAtrasados(materiaId, cohorteId),
  })
}
