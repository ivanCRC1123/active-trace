import { useQuery } from '@tanstack/react-query'
import { getMeAsignaciones } from '../services/meService'

export function useMeAsignaciones() {
  return useQuery({
    queryKey: ['me', 'asignaciones'],
    queryFn: getMeAsignaciones,
  })
}
