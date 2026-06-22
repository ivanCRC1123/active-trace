# C-22 frontend-academico-docente — Proposal

## Contexto

El backend del camino crítico está completo: C-10 (calificaciones + umbral), C-11 (análisis,
atrasados, monitor, notas finales, sin corregir), C-12 (comunicaciones con cola y worker).
El frontend de C-21 provee la infra completa: Axios + interceptor JWT/refresh, sessionStore,
`ProtectedRoute` con permiso, `AppShell` con menú filtrado, TanStack Query, React Hook Form + Zod.

C-22 construye la interfaz del flujo central del PROFESOR (FL-02): importar → analizar → comunicar.

## Dependencias

- **C-21 (DONE)**: infra frontend — `api.ts`, `sessionStore`, `ProtectedRoute`, `AppShell`
- **C-10 (DONE)**: endpoints calificaciones + umbral
- **C-11 (DONE)**: endpoints análisis, atrasados, ranking, reportes, monitor, sin corregir
- **C-12 (DONE)**: endpoints comunicaciones, preview, lotes, aprobación

## Alcance confirmado

### Épica 1 — Importación
- **F1.1** Importar calificaciones: upload xlsx → preview actividades → selector → confirm + umbral
- **F1.2** Importar reporte de finalización: upload → persiste FinalizacionActividad → ver sin corregir

### Épica 2 — Análisis y Reportes
- **F2.1** Configurar umbral de aprobación (inline en ImportarPage)
- **F2.2** Ver alumnos atrasados (AtrasadosPage, tabla con faltantes + bajo umbral)
- **F2.3** Ranking de actividades aprobadas (RankingPage)
- **F2.4** Reportes rápidos por materia (MateriaDashboardPage con KPIs)
- **F2.5** Notas finales agrupadas + export CSV (NotasFinalesPage)
- **F2.6** Exportar trabajos prácticos sin corregir (SinCorregirPage, CSV)
- **F2.7/F2.8/F2.9** Monitor unificado con scope automático por rol (MonitorPage)

### Épica 3 — Comunicaciones
- **F3.1** Vista previa obligatoria antes de envío (preview modal)
- **F3.2** Envío masivo con cola y tracking de estados (NuevaComunicacionPage + ComunicacionesPage)
- **F3.3** Aprobación de lotes masivos (panel dentro de ComunicacionesPage, visible solo con `comunicacion:aprobar`)

## Non-Goals

- F3.4 Mensajería interna (bandeja del docente) → change futuro
- F3.5 Tablón de avisos → change futuro
- Épica 4 equipos docentes → C-23
- Épica 5 estructura académica → change separado
- Épica 6 encuentros → change futuro
- Portal del alumno → fuera de scope MVP
- Enrollment 2FA desde perfil → C-22 o change de perfil

## Pantallas propuestas (11)

| Pantalla | Ruta | Permiso guard |
|----------|------|---------------|
| CalificacionesHomePage | `/calificaciones` | `calificaciones:importar` |
| MateriaDashboardPage | `/calificaciones/:materiaId/:cohorteId` | `atrasados:ver` |
| ImportarPage | `/calificaciones/:materiaId/:cohorteId/importar` | `calificaciones:importar` |
| AtrasadosPage | `/calificaciones/:materiaId/:cohorteId/atrasados` | `atrasados:ver` |
| RankingPage | `/calificaciones/:materiaId/:cohorteId/ranking` | `atrasados:ver` |
| NotasFinalesPage | `/calificaciones/:materiaId/:cohorteId/notas-finales` | `atrasados:ver` |
| SinCorregirPage | `/calificaciones/:materiaId/:cohorteId/sin-corregir` | `atrasados:ver` |
| MonitorPage | `/monitor` | `atrasados:ver` |
| ComunicacionesPage | `/comunicaciones` | `comunicacion:enviar` |
| NuevaComunicacionPage | `/comunicaciones/nuevo` | `comunicacion:enviar` |
| LoteDetallePage | `/comunicaciones/lotes/:loteId` | `comunicacion:enviar` |

## Endpoints reales consumidos

### C-10 — Calificaciones y Umbral
| Método | Endpoint | Feature |
|--------|----------|---------|
| POST | `/api/v1/calificaciones/{mid}/cohortes/{cid}/importar` | ImportarPage (preview + confirm) |
| DELETE | `/api/v1/calificaciones/{mid}/cohortes/{cid}/vaciar` | ImportarPage (acción vaciar) |
| GET | `/api/v1/umbral/{mid}` | ImportarPage (carga umbral actual) |
| PUT | `/api/v1/umbral/{mid}` | ImportarPage (guarda umbral) |

### C-11 — Análisis
| Método | Endpoint | Feature |
|--------|----------|---------|
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/atrasados` | AtrasadosPage |
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/ranking` | RankingPage |
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/reportes-rapidos` | MateriaDashboardPage |
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales` | NotasFinalesPage |
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales/exportar` | NotasFinalesPage (CSV) |
| POST | `/api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion` | SinCorregirPage (upload) |
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir` | SinCorregirPage |
| GET | `/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir/exportar` | SinCorregirPage (CSV) |
| GET | `/api/v1/analisis/monitor` | MonitorPage |

### C-12 — Comunicaciones
| Método | Endpoint | Feature |
|--------|----------|---------|
| POST | `/api/v1/comunicaciones/preview` | NuevaComunicacionPage (modal) |
| POST | `/api/v1/comunicaciones/lotes` | NuevaComunicacionPage (envío) |
| GET | `/api/v1/comunicaciones/lotes/{lote_id}` | LoteDetallePage |
| POST | `/api/v1/comunicaciones/lotes/{lote_id}/aprobar` | ComunicacionesPage (panel aprobación) |
| POST | `/api/v1/comunicaciones/lotes/{lote_id}/cancelar` | ComunicacionesPage (panel aprobación) |
| POST | `/api/v1/comunicaciones/{com_id}/cancelar` | LoteDetallePage |
| GET | `/api/v1/comunicaciones` | ComunicacionesPage |

## Permission codes en esta feature

| Código | Roles | Scope | Dónde se usa |
|--------|-------|-------|--------------|
| `calificaciones:importar` | PROFESOR(own), COORDINADOR(all), ADMIN(all) | scope | ImportarPage, UmbralForm, VaciarDatos |
| `atrasados:ver` | TUTOR(own), PROFESOR(own), COORDINADOR(all), ADMIN(all) | scope | Todas las páginas de análisis y Monitor |
| `comunicacion:enviar` | PROFESOR(own), COORDINADOR(all), ADMIN(all) | scope | ComunicacionesPage, NuevaComunicacionPage, LoteDetallePage |
| `comunicacion:aprobar` | COORDINADOR(all), ADMIN(all) | all | AprobacionPanel (visible condicionalmente) |

## Decisiones abiertas (ver design.md OQs)

- **OQ-C22-01 (BLOQUEANTE)**: No existe endpoint para que el PROFESOR consulte sus propias asignaciones activas.
- **OQ-C22-02**: Navegación intra-materia: tabs vs. rutas con nav secundaria.
- **OQ-C22-03**: Flujo envío desde AtrasadosPage: ruta separada vs. drawer/modal.
- **OQ-C22-04**: SinCorregirPage: endpoint C-11 (persiste) vs. C-10 (no persiste).
- **OQ-C22-05**: Monitor en AppShell: ítem propio vs. sub-ruta de Calificaciones.
- **OQ-C22-06**: Plantilla de comunicación: texto libre vs. plantilla pre-cargada con variables.
