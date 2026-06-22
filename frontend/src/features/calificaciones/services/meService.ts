import { api } from '@/shared/services/api'
import type { MeAsignacionItem } from '../types/me.types'

export async function getMeAsignaciones(): Promise<MeAsignacionItem[]> {
  const res = await api.get<MeAsignacionItem[]>('/v1/me/asignaciones')
  return res.data
}
