# C-11 — analisis-atrasados-reportes: Proposal

## Why

Con C-10 el sistema tiene calificaciones por alumno×actividad con el flag `aprobado`
materializado. Lo que falta es la capa de **análisis**: computar qué alumnos están atrasados,
ordenar el ranking de actividades aprobadas, generar notas finales, detectar trabajos prácticos
sin corregir y exponer monitores transversales. Sin esta capa no hay insumo para C-12
(comunicaciones) ni para la vista de coordinación.

C-11 también cierra la deuda de **F1.2 (importar reporte de finalización)**, que fue diferida
de C-10 por decisión de diseño (OQ-C10-3): el endpoint `importar-finalizacion` pertenece aquí
porque su salida útil es precisamente el cruce con calificaciones que da la tabla
"sin corregir" (RN-07/08).

## What Changes

### Nuevo modelo: FinalizacionActividad (E-FIN)

Persiste el estado de finalización por alumno×actividad tal como lo reporta el LMS. Un row
por `(entrada_padron_id, actividad, asignacion_id)`. Permite cruzar con `Calificacion` para
detectar entregas sin calificar (RN-07/08) sin re-subir el archivo cada vez.

### Migración 009

Crea la tabla `finalizacion_actividad` con FK a `entrada_padron`, `materia`, `asignacion` y
`tenant`. Índices para el cruce con `calificacion`.

### Parser de finalización

`backend/app/services/finalizacion_parser.py`: parsea el reporte de finalización del LMS
(xlsx/csv). Detecta la columna de email (mismo alias que padron/calificaciones parser),
y columnas de actividades con valores de estado de finalización.

El reporte de finalización de Moodle tiene una columna por actividad con valores como
`"Completado"` / `"No completado"` (o sus equivalentes en inglés). El parser las mapea a
`True/False` con un vocabulario configurable de valores completados.

### FinalizacionRepository

`vaciar_por_asignacion_materia`, `bulk_insert`, `list_sin_corregir` (cruce con calificaciones,
solo actividades textuales — RN-08).

### AnalisisRepository

Queries complejas que cruzan `Calificacion`, `EntradaPadron`, `VersionPadron` y
`FinalizacionActividad`:
- `atrasados(materia_id, cohorte_id, asignacion_id?)` — RN-06
- `ranking(materia_id, cohorte_id, asignacion_id?)` — RN-09
- `notas_finales(materia_id, cohorte_id, asignacion_id?)` — F2.5
- `reporte_rapido(materia_id, cohorte_id, asignacion_id?)` — F2.4
- `monitor(filters)` — F2.7/F2.8/F2.9

Toda la lógica SQL vive en el repositorio; el servicio solo orquesta.

### AnalisisService

Orquesta finalizacion import + queries de análisis. Resuelve el scope (own vs all) según los
permisos de la sesión.

### Endpoints `/api/v1/analisis/`

| Método | Path | Permiso | Funcionalidad |
|--------|------|---------|---------------|
| POST | `/{materia_id}/cohortes/{cohorte_id}/importar-finalizacion` | `calificaciones:importar` | F1.2 — import reporte finalización |
| GET | `/{materia_id}/cohortes/{cohorte_id}/atrasados` | `atrasados:ver` | F2.2 |
| GET | `/{materia_id}/cohortes/{cohorte_id}/ranking` | `atrasados:ver` | F2.3 |
| GET | `/{materia_id}/cohortes/{cohorte_id}/reportes-rapidos` | `atrasados:ver` | F2.4 |
| GET | `/{materia_id}/cohortes/{cohorte_id}/notas-finales` | `atrasados:ver` | F2.5 |
| GET | `/{materia_id}/cohortes/{cohorte_id}/notas-finales/exportar` | `atrasados:ver` | F2.5 export CSV |
| GET | `/{materia_id}/cohortes/{cohorte_id}/sin-corregir` | `atrasados:ver` | F2.6 |
| GET | `/{materia_id}/cohortes/{cohorte_id}/sin-corregir/exportar` | `atrasados:ver` | F2.6 export CSV |
| GET | `/monitor` | `atrasados:ver` | F2.7/F2.8/F2.9 (unificado, scope por rol) |

### Permisos nuevos (seed)

| Permiso | TUTOR | PROFESOR | COORDINADOR | ADMIN |
|---------|-------|----------|-------------|-------|
| `atrasados:ver` | scope=own | scope=own | scope=all | scope=all |

## New Capabilities

- **F1.2**: Importar reporte de finalización → detecta TPs entregados sin nota.
- **F2.2**: Alumnos atrasados — faltantes y bajo umbral por materia×cohorte.
- **F2.3**: Ranking de actividades aprobadas (solo alumnos con ≥1 aprobada, RN-09).
- **F2.4**: Reporte rápido — métricas de estado de la comisión en una vista.
- **F2.5**: Notas finales agrupadas + export CSV.
- **F2.6**: Tabla "sin corregir" (solo actividades textuales, RN-08) + export CSV.
- **F2.7/F2.8/F2.9**: Monitor unificado con scope automático por rol y filtros opcionales.

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Migration | `[rev]_009_finalizacion_actividad.py` | +1 |
| Models | `finalizacion_actividad.py` (new) | +1 |
| Models | `models/__init__.py` | modify |
| Services | `finalizacion_parser.py` (new), `analisis_service.py` (new) | +2 |
| Repositories | `finalizacion_repository.py` (new), `analisis_repository.py` (new) | +2 |
| Schemas | `analisis.py` (new) | +1 |
| Routers | `analisis.py` (new) | +1 |
| main.py | register analisis router | modify |
| seed | `scripts/seed_permissions.py` | modify |
| Tests | `conftest.py` (añadir limpieza finalizacion_actividad) | modify |
| Tests | `test_finalizacion_parser.py` (new), `test_analisis.py` (new) | +2 (~40 tests) |

## Dependencies

- **C-10**: tabla `calificacion` (flag `aprobado` materializado) + `umbral_materia` + parser base.
- **C-09**: tabla `entrada_padron` (FK de `finalizacion_actividad`) + `version_padron`.
- **C-07**: tabla `asignacion` (scope isolation, RN-04).
- **C-05**: `AuditService` para `CALIFICACIONES_IMPORTAR` (reutilizado en finalizacion import).
- C-11 **desbloquea**: C-12 (comunicaciones, consume la lista de atrasados).

## Open Questions

| ID | Pregunta | Impacto si no se resuelve |
|----|----------|--------------------------|
| OQ-C11-1 | ¿Qué vocabulario usa el reporte de finalización de Moodle para "completado"? Propuesta: `{"Completado", "Completed", "Sí", "Yes", "True", "1"}` como default configurable. | El parser no detecta entregas correctamente si el vocabulario difiere. |
| OQ-C11-2 | ¿"Nota final" (F2.5) se calcula como % de actividades aprobadas o como promedio de notas numéricas? Propuesta: `aprobadas / total_actividades × 100`. | La columna "nota final" en el export puede no coincidir con el criterio real del docente. |
| OQ-C11-3 | ¿El monitor unificado (F2.7/F2.8/F2.9) necesita paginación? Con > 500 alumnos la respuesta puede ser grande. Propuesta: paginación por defecto (`limit=100`, `offset=0`). | Sin paginación la UI puede tener timeouts con comisiones grandes. |
| OQ-C11-4 | ¿"Faltante" = alumno sin calificacion para una actividad que OTROS alumnos sí tienen, o solo el que tiene `aprobado=False`? Ver D-C11-3. | La definición afecta directamente cuántos alumnos aparecen como "atrasados". |

## Governance

**MEDIO** — lógica de análisis académico sobre datos existentes. Implementar con checkpoints:
surfacear OQ-C11-1 (vocabulario de finalización) y OQ-C11-4 (definición de faltante) antes
de escribir el repositorio de atrasados.
