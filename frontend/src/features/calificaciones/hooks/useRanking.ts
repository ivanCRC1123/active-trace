import { useQuery } from '@tanstack/react-query'
import { calificacionesService } from '../services/calificacionesService'

export function useRanking(materiaId: string, cohorteId: string) {
  return useQuery({
    queryKey: ['ranking', materiaId, cohorteId],
    queryFn: () => calificacionesService.getRanking(materiaId, cohorteId),
  })
}
