export interface MonitorItem {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  regional: string | null
  materia_id: string
  cohorte_id: string
  estado: 'atrasado' | 'al_dia'
  actividades_faltantes: string[]
  actividades_bajo_umbral: string[]
  total_aprobadas: number
  total_calificaciones: number
}

export interface MonitorResponse {
  items: MonitorItem[]
  total: number
  limit: number
  offset: number
}

export interface MonitorFilters {
  materia_id?: string
  cohorte_id?: string
  alumno?: string
  comision?: string
  regional?: string
  estado?: 'atrasado' | 'al_dia'
  fecha_desde?: string
  fecha_hasta?: string
  limit?: number
  offset?: number
}
