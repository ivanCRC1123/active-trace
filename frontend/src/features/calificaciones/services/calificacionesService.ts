import { api } from '@/shared/services/api'
import type {
  AtrasadosResponse,
  GradePreview,
  ImportarCalificacionesResult,
  NotasFinalesResponse,
  RankingResponse,
  UmbralMateriaRequest,
  UmbralMateriaResponse,
  VaciarResult,
} from '../types/calificaciones.types'

const base = (materiaId: string, cohorteId: string) =>
  `/v1/calificaciones/${materiaId}/cohortes/${cohorteId}`

const analisisBase = (materiaId: string, cohorteId: string) =>
  `/v1/analisis/${materiaId}/cohortes/${cohorteId}`

export const calificacionesService = {
  preview(materiaId: string, cohorteId: string, file: File): Promise<GradePreview> {
    const fd = new FormData()
    fd.append('file', file)
    return api
      .post<GradePreview>(`${base(materiaId, cohorteId)}/preview`, fd)
      .then((r) => r.data)
  },

  importar(
    materiaId: string,
    cohorteId: string,
    file: File,
    actividades: string[],
  ): Promise<ImportarCalificacionesResult> {
    const fd = new FormData()
    fd.append('file', file)
    const qs = new URLSearchParams()
    actividades.forEach((a) => qs.append('actividades_seleccionadas', a))
    return api
      .post<ImportarCalificacionesResult>(
        `${base(materiaId, cohorteId)}/importar?${qs.toString()}`,
        fd,
      )
      .then((r) => r.data)
  },

  getUmbral(materiaId: string, cohorteId: string): Promise<UmbralMateriaResponse> {
    return api
      .get<UmbralMateriaResponse>(`${base(materiaId, cohorteId)}/umbral`)
      .then((r) => r.data)
  },

  putUmbral(
    materiaId: string,
    cohorteId: string,
    data: UmbralMateriaRequest,
  ): Promise<UmbralMateriaResponse> {
    return api
      .put<UmbralMateriaResponse>(`${base(materiaId, cohorteId)}/umbral`, data)
      .then((r) => r.data)
  },

  vaciar(materiaId: string, cohorteId: string): Promise<VaciarResult> {
    return api
      .delete<VaciarResult>(`${base(materiaId, cohorteId)}/vaciar`)
      .then((r) => r.data)
  },

  getAtrasados(materiaId: string, cohorteId: string): Promise<AtrasadosResponse> {
    return api
      .get<AtrasadosResponse>(`${analisisBase(materiaId, cohorteId)}/atrasados`)
      .then((r) => r.data)
  },

  getRanking(materiaId: string, cohorteId: string): Promise<RankingResponse> {
    return api
      .get<RankingResponse>(`${analisisBase(materiaId, cohorteId)}/ranking`)
      .then((r) => r.data)
  },

  getNotasFinales(materiaId: string, cohorteId: string): Promise<NotasFinalesResponse> {
    return api
      .get<NotasFinalesResponse>(`${analisisBase(materiaId, cohorteId)}/notas-finales`)
      .then((r) => r.data)
  },

  exportarNotasFinales(materiaId: string, cohorteId: string): Promise<Blob> {
    return api
      .get<Blob>(`${analisisBase(materiaId, cohorteId)}/notas-finales/exportar`, {
        responseType: 'blob',
      })
      .then((r) => r.data)
  },
}
