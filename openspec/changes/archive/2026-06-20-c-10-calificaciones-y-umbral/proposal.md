# C-10 — calificaciones-y-umbral: Proposal

## Why

El padrón de alumnos existe (C-09), pero el sistema no tiene aún ningún dato sobre su
rendimiento académico. Sin calificaciones no hay "alumnos atrasados" (C-11), y sin
atrasados no hay comunicaciones automatizadas (C-12). C-10 cierra esa brecha: toma el
archivo de calificaciones exportado desde el LMS y lo convierte en registros por
alumno × actividad, comparados contra el criterio de aprobación que configura cada docente.

## What Changes

### Modelos nuevos

- **Calificacion (E7)**: un registro por alumno × actividad evaluable dentro de una materia.
  Guarda la nota numérica y/o textual, el campo `aprobado` (calculado en el momento de la
  importación contra el umbral vigente) y el `asignacion_id` del docente que importó (permite
  scope isolation por RN-04). FK a `EntradaPadron` garantiza que solo se califican alumnos
  del padrón activo.

- **UmbralMateria (E8)**: criterio de aprobación configurado por el docente para su
  asignación en una materia. Almacena `umbral_pct` (defecto 60, configurable por RN-03) y
  `valores_aprobatorios` (lista de strings JSON, defecto `["Satisfactorio", "Supera lo esperado"]`
  según RN-02). Un solo `UmbralMateria` por `(asignacion_id, materia_id)` — al actualizar el
  umbral se actualiza el mismo registro (no se versionan).

### Migración 008

- Crea las tablas `calificacion` y `umbral_materia`.
- `down_revision = "a1b2c3d4e5f6"` (migración 007, C-09).

### Parser de calificaciones

- **`backend/app/services/calificaciones_parser.py`**: analiza un xlsx exportado del LMS.
  - Detecta columnas de nota numérica: encabezado termina en `(Real)` (RN-01).
  - Detecta columnas textuales: cualquier otra columna que no sea de infraestructura (email,
    nombre, apellidos, grupo, etc.) y que contenga valores del vocabulario textual.
  - La columna de identificación del alumno se busca por alias (igual que padron_parser:
    `email`, `correo`, `mail`, etc.).
  - Retorna: lista de actividades detectadas (con tipo: `numerica` | `textual`) + filas
    por alumno, sin escribir en DB. Permite al cliente hacer preview y seleccionar actividades.

### Parser de finalización (F1.2)

- El mismo `calificaciones_parser.py` expone una función `parse_finalizacion_file()`:
  detecta si un alumno tiene una actividad en estado "finalizado" pero sin calificación
  registrada. Cruza el archivo de finalización del LMS con las calificaciones ya importadas
  (RN-07, RN-08).

### Endpoints

- `POST /api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}/importar`
  multipart (`archivo`) + JSON body `{ actividades: [str], preview: bool }`.
  Preview retorna `CalificacionesPreview`. Confirm retorna `CalificacionesImportResult`.
  Guard: `calificaciones:importar`.

- `POST /api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}/importar-finalizacion`
  multipart (`archivo`). Retorna `FinalizacionResult` (lista de actividades sin corregir).
  Guard: `calificaciones:importar`.

- `GET /api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}`
  Devuelve calificaciones del padrón activo para la asignación del usuario actual.
  Guard: `calificaciones:ver`.

- `DELETE /api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}/vaciar`
  Elimina (soft-delete) las calificaciones importadas por el usuario actual en esa materia.
  PROFESOR (scope=own): solo las suyas. COORDINADOR/ADMIN (scope=all): todas.
  Guard: `calificaciones:importar`.

- `GET /api/v1/umbral/{materia_id}`
  Devuelve el UmbralMateria del usuario actual para esa materia (o los defaults si no existe).
  Guard: `calificaciones:importar`.

- `PUT /api/v1/umbral/{materia_id}`
  Upsert del UmbralMateria. Guard: `calificaciones:importar`.

### Derivación de `aprobado` (regla central)

```
si nota_numerica is not None:
    aprobado = nota_numerica >= umbral_pct
    # Asunción: el LMS exporta notas en escala 0–100 (porcentaje).
    # umbral_pct = 60 significa nota >= 60.00 → aprobado.
    # Ver OQ-C10-1 sobre la escala de notas.
else:
    aprobado = nota_textual in valores_aprobatorios
    # Default: {"Satisfactorio", "Supera lo esperado"}
```

El valor se calcula en el servicio al importar y se persiste. Si el umbral cambia
después de una importación, el campo `aprobado` de registros existentes NO se recalcula
(ver OQ-C10-2). El docente re-importa para forzar el recálculo.

### Auditoría

Usa el código `CALIFICACIONES_IMPORTAR` ya definido en `audit_codes.py`. Se registra
tras cada importación exitosa con: `materia_id`, `cohorte_id`, `asignacion_id`,
`actividades_importadas`, `total_calificaciones`, `total_aprobadas`.

### Permisos nuevos (seed)

| Permiso | PROFESOR | COORDINADOR | ADMIN |
|---------|----------|-------------|-------|
| `calificaciones:importar` | scope=own | scope=all | scope=all |
| `calificaciones:ver` | scope=own | scope=all | scope=all |

## New Capabilities

- `calificaciones:parse-preview` — parsear xlsx sin escribir en DB; retornar actividades
  detectadas y muestra de alumnos para que el PROFESOR seleccione qué incluir.
- `calificaciones:import-confirm` — importar actividades seleccionadas, calcular `aprobado`
  con el umbral vigente, persisitir calificaciones y emitir audit.
- `calificaciones:import-finalizacion` — detectar entregas sin corregir cruzando el reporte
  de finalización del LMS con calificaciones ya importadas (RN-07, RN-08).
- `calificaciones:umbral-config` — PROFESOR configura umbral_pct y valores_aprobatorios
  por materia (RN-03); sin umbral configurado aplica el default de 60%.
- `calificaciones:vaciar` — PROFESOR vacía sus propias calificaciones en una materia (RN-04);
  COORDINADOR/ADMIN puede vaciar cualquiera.

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Migration | `[rev]_008_calificacion_umbral.py` | +1 |
| Models | `calificacion.py` (new), `umbral_materia.py` (new) | +2 |
| Services | `calificaciones_service.py` (new), `calificaciones_parser.py` (new) | +2 |
| Repositories | `calificacion_repository.py` (new), `umbral_materia_repository.py` (new) | +2 |
| Schemas | `calificaciones.py` (new) | +1 |
| Routers | `calificaciones.py` (new) | +1 |
| main.py | register router | modify |
| audit_codes.py | `CALIFICACIONES_IMPORTAR` ya existe — no hay que modificar | — |
| seed | `scripts/seed_permissions.py` | modify |
| Tests | `test_calificaciones.py` (new), `test_calificaciones_parser.py` (new) | +2 (~30 tests) |

## Dependencies

- **C-09** (padron): tabla `entrada_padron` — FK de `calificacion.entrada_padron_id`.
  Sin padrón activo no se puede importar calificaciones (400 si no hay versión activa).
- **C-07** (usuarios): tabla `asignacion` — FK de `umbral_materia.asignacion_id` y
  `calificacion.asignacion_id`. El scope isolation (RN-04) se basa en `asignacion_id`.
- **C-05** (audit log): `AuditService` para registrar `CALIFICACIONES_IMPORTAR`.
- C-10 **desbloquea**: C-11 (análisis-atrasados) que consume `Calificacion.aprobado` y `UmbralMateria`.

## Open Questions

| ID | Pregunta | Impacto si no se resuelve |
|----|----------|--------------------------|
| OQ-C10-1 | ¿El LMS exporta notas en escala 0–100 o 0–10? La derivación de `aprobado` cambia: con escala 0–100, `nota >= umbral_pct`; con 0–10, `nota >= umbral_pct / 10`. | La fórmula de aprobación es incorrecta en producción. |
| OQ-C10-2 | ¿Si el docente cambia el umbral después de importar, deben recalcularse los `aprobado` existentes? | Los atrasados en C-11 quedarían desincronizados. La propuesta (re-importar) es pragmática pero requiere UX clara. |
| OQ-C10-3 | ¿El "reporte de finalización" (F1.2) es un archivo separado del de calificaciones, o una hoja del mismo xlsx? | Cambia si hay un endpoint separado o si es una detección automática al importar calificaciones. |

## Governance

**MEDIO** — datos académicos de alumnos (notas). Implementar con checkpoints:
surfacear OQ-C10-1 (escala de notas) antes de implementar la derivación de `aprobado`.
La regla de derivación es el núcleo del change; si está mal, C-11 y C-12 producen
resultados incorrectos en producción.
