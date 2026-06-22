import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { calificacionesService } from '../services/calificacionesService'
import type { UmbralMateriaRequest } from '../types/calificaciones.types'

export function useUmbral(materiaId: string, cohorteId: string) {
  const qc = useQueryClient()

  const query = useQuery({
    queryKey: ['umbral', materiaId, cohorteId],
    queryFn: () => calificacionesService.getUmbral(materiaId, cohorteId),
  })

  const mutation = useMutation({
    mutationFn: (data: UmbralMateriaRequest) =>
      calificacionesService.putUmbral(materiaId, cohorteId, data),
    onSuccess: (updated) => {
      qc.setQueryData(['umbral', materiaId, cohorteId], updated)
    },
  })

  return { ...query, update: mutation }
}
