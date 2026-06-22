export interface MeAsignacionItem {
  id: string
  materia_id: string | null
  materia_nombre: string | null
  carrera_id: string | null
  carrera_nombre: string | null
  cohorte_id: string | null
  cohorte_nombre: string | null
  comisiones: unknown[]
  rol_nombre: string
  desde: string
  hasta: string | null
}
