export type EstadoComunicacion = 'PENDIENTE' | 'ENVIANDO' | 'ENVIADO' | 'ERROR' | 'CANCELADO'

export interface PreviewRequest {
  destinatarios: string[]
  materia_id: string
  cohorte_id: string
  asunto_template: string
  cuerpo_template: string
}

export interface PreviewItem {
  entrada_padron_id: string
  nombre: string
  apellidos: string
  asunto_renderizado: string
  cuerpo_renderizado: string
}

export interface PreviewResponse {
  items: PreviewItem[]
}

export interface CrearLoteRequest {
  destinatarios: string[]
  materia_id: string
  cohorte_id: string
  asunto_template: string
  cuerpo_template: string
}

export interface LoteCreado {
  lote_id: string
  total_encolados: number
  requiere_aprobacion: boolean
}

export interface ResumenEstados {
  PENDIENTE: number
  ENVIANDO: number
  ENVIADO: number
  ERROR: number
  CANCELADO: number
}

export interface ComunicacionItem {
  id: string
  entrada_padron_id: string | null
  nombre: string | null
  apellidos: string | null
  estado: EstadoComunicacion
  enviado_at: string | null
  aprobado_at: string | null
}

export interface LoteDetalle {
  lote_id: string
  materia_id: string
  enviado_por: string
  resumen_estados: ResumenEstados
  items: ComunicacionItem[]
}

export interface ComunicacionListResponse {
  items: ComunicacionItem[]
  total: number
}
