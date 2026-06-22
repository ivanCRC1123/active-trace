export interface ActividadDetectada {
  nombre: string
  tipo: 'numerica' | 'textual'
  total_notas: number
}

export interface CalificacionesPreview {
  actividades_detectadas: ActividadDetectada[]
  alumnos_detectados: number
  advertencias: string[]
}

export interface CalificacionesImportResult {
  actividades_importadas: number
  calificaciones_creadas: number
  calificaciones_actualizadas: number
  total_aprobadas: number
  advertencias: string[]
}

export interface UmbralMateriaResponse {
  id: string | null
  asignacion_id: string | null
  materia_id: string
  umbral_pct: number
  valores_aprobatorios: string[]
  es_default: boolean
}

export interface AlumnoAtrasado {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  regional: string | null
  actividades_faltantes: string[]
  actividades_bajo_umbral: string[]
}

export interface AtrasadosResponse {
  total_alumnos: number
  total_atrasados: number
  atrasados: AlumnoAtrasado[]
}

export interface RankingItem {
  posicion: number
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  total_aprobadas: number
  total_calificaciones: number
}

export interface NotaFinalAlumno {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  aprobadas: number
  total_calificaciones: number
  nota_final_pct: number | null
}

export interface EntregaSinCorregir {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  comision: string | null
  actividad: string
}

export interface SinCorregirResponse {
  items: EntregaSinCorregir[]
  total: number
  aviso: string | null
}

export interface ReporteRapidoResponse {
  total_alumnos: number
  total_actividades: number
  total_aprobaciones: number
  total_desaprobaciones: number
  alumnos_con_desaprobacion: number
  alumnos_atrasados: number
  tiene_datos: boolean
}
