# C-08 — equipos-docentes: Proposal

## Why

C-07 creó el modelo `Asignacion` (E5) y su CRUD raw (`/api/v1/asignaciones`). Pero el negocio
opera con _equipos_: conjuntos de asignaciones que comparten un contexto `(materia × carrera ×
cohorte)` y que se gestionan en bloque al inicio de cada cuatrimestre.

Sin C-08, un COORDINADOR que quiere arrancar el nuevo cuatrimestre tiene que:
- Crear asignaciones de a una (N docentes × M materias = N×M peticiones).
- No tiene forma de clonar el equipo del período anterior (RN-12).
- No puede ajustar la vigencia de todo el equipo en una sola operación.
- Un PROFESOR ni siquiera puede ver en qué materias/cohortes está asignado.

C-08 cubre **FL-03 (setup de inicio de cuatrimestre)** completo: el flujo estrella del
COORDINADOR que ejecuta N veces por año.

## What Changes

### Sin migración — puramente service/router sobre `asignacion` existente

No hay nuevas tablas. C-08 es un cambio de capa de aplicación: nuevos endpoints y service methods
que operan sobre la tabla `asignacion` ya creada por C-07.

### Nuevo permiso `equipos:ver` en seed

F4.2 ("mis equipos") es accesible por PROFESOR, TUTOR, NEXO, COORDINADOR — roles que actualmente
no tienen forma de leer sus propias asignaciones sin `equipos:asignar` (que otorga CRUD completo).
Se añade `equipos:ver` (own) para esos roles, y (all) para COORDINADOR/ADMIN.

### Nuevos endpoints — `/api/v1/equipos/`

| Método | Ruta | Guard | Descripción |
|--------|------|-------|-------------|
| `GET` | `/equipos/mis-equipos` | `equipos:ver` | Propias asignaciones con filtros (F4.2) |
| `GET` | `/equipos` | `equipos:asignar` | Todas las asignaciones del tenant con filtros ricos (F4.3) |
| `POST` | `/equipos/masiva` | `equipos:asignar` | Alta masiva (múltiples docentes, un contexto) (F4.4) |
| `POST` | `/equipos/clonar` | `equipos:asignar` | Clonar equipo entre cohortes (F4.5, RN-12) |
| `PATCH` | `/equipos/vigencia` | `equipos:asignar` | Ajustar vigencia del equipo en bloque (F4.6) |
| `GET` | `/equipos/exportar` | `equipos:asignar` | CSV con el equipo completo (F4.7) |

### Nuevos service methods en `EquipoService`

- `mis_equipos(usuario_id, tenant_id, filtros) → list[AsignacionResponse]`
- `list_equipo(tenant_id, filtros) → list[AsignacionResponse]`
- `asignar_masiva(tenant_id, payload) → MasivaResult`
- `clonar_equipo(tenant_id, payload) → ClonarResult`
- `actualizar_vigencia_bloque(tenant_id, payload) → int` (filas afectadas)
- `exportar_csv(tenant_id, filtros) → bytes`

## New Capabilities

- `equipos:ver (propio)` — PROFESOR/TUTOR/NEXO pueden consultar sus propias asignaciones.
- `mis-equipos` — Vista personal del docente: qué materias/cohortes/roles tiene asignados.
- `masiva` — COORDINADOR puede asignar N docentes a un contexto en una sola operación.
- `clonar` — Feature estrella: copia el equipo vigente de la cohorte anterior a la nueva.
- `vigencia-bloque` — Ajuste de fechas de todo el equipo sin tocar uno por uno.
- `exportar` — CSV descargable con el equipo completo para distribución o archivo.

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Seed | `scripts/seed_permissions.py` | Agrega `equipos:ver` (permiso + matrix) |
| Service | `app/services/equipo_service.py` (nuevo) | +1 |
| Router | `app/api/v1/routers/equipos.py` (nuevo) | +1 |
| Schemas | `app/schemas/equipos.py` (nuevo) | +1 |
| main.py | Registrar router equipos | modify |
| Tests | `tests/test_equipos.py` (nuevo) | +1 (~40 tests) |

No se toca `asignacion.py` (modelo), `asignacion_repository.py` ni la migración de C-07.

## Dependencies

- **C-07**: tablas `asignacion`, `user` y repositorio base `AsignacionRepository` ya existentes.
- **C-05**: helper `AuditService` para registrar `ASIGNACION_MODIFICAR`.
- C-08 **desbloquea**: C-23 (frontend-coordinacion, que consume estos endpoints).

## Governance

**ALTO** — modifica asignaciones que determinan quién tiene permisos sobre qué materias.
Implementar con checkpoints; las operaciones masivas (masiva, clonar, vigencia-bloque) deben
ser transaccionales y respetar el scope de tenant en cada row.
