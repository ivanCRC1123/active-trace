# C-16 — tareas-internas: Proposal

## Why

C-07 creó `Usuario` y `Asignacion`. Los módulos que vinieron después (C-08, C-13, etc.) construyeron
sobre esas entidades los flujos de dominio. C-16 cierra la brecha de coordinación interna del equipo
docente: la capacidad de registrar, asignar y hacer seguimiento de tareas operativas entre los
miembros del equipo.

Sin C-16, el equipo docente no tiene dentro del sistema un lugar donde:
- Un COORDINADOR pueda asignar a un TUTOR "revisá los avances de la comisión B antes del jueves".
- Un PROFESOR pueda delegar a otro "completá el registro de notas finales de la cohorte AGO-2025".
- Un TUTOR pueda ver las tareas que le fueron delegadas y marcarlas como resueltas.
- Coordinación pueda ver el estado global del workflow y detectar tareas bloqueadas.

C-16 cubre la **Épica 8 completa** (F8.1 – F8.3): el workflow de tareas internas entre roles
docentes y de coordinación.

## What Changes

### 2 tablas nuevas + migración

| Tabla | Entidad KB | Descripción |
|-------|-----------|-------------|
| `tarea` | E12 Tarea | Tarea asignada, con estado FSM y referencia contextual opcional |
| `comentario_tarea` | E12 ComentarioTarea | Hilo de comentarios sobre una tarea |

Migración Alembic: `Migración 0NN: tarea, comentario_tarea`.

### Nuevos endpoints — `/api/v1/tareas/`

| Método | Ruta | Guard | Quién | Descripción |
|--------|------|-------|-------|-------------|
| `GET` | `/tareas/mis-tareas` | identity (JWT) | todos los roles autenticados | Tareas donde soy `asignado_a` (F8.1) |
| `POST` | `/tareas` | `tareas_internas:gestionar` | PROFESOR (own), COORDINADOR, ADMIN | Crear y asignar tarea (F8.2) |
| `PATCH` | `/tareas/{id}/estado` | identity + ownership check | asignado_a (self), asignado_por (self), gestores | Cambiar estado FSM |
| `GET` | `/tareas` | `tareas_internas:gestionar` | COORDINADOR, ADMIN | Vista global con filtros (F8.3) |
| `POST` | `/tareas/{id}/comentarios` | identity + membership check | asignado_a, asignado_por, gestores | Agregar comentario |
| `GET` | `/tareas/{id}/comentarios` | identity + membership check | asignado_a, asignado_por, gestores | Leer hilo de comentarios |
| `GET` | `/tareas/{id}` | identity + membership check | asignado_a, asignado_por, gestores | Detalle de una tarea |

### Nuevos service methods en `TareaService`

- `mis_tareas(usuario_id, tenant_id, filtros) → list[TareaResponse]`
- `crear_tarea(tenant_id, payload, current_user) → TareaResponse`
- `cambiar_estado(tarea_id, tenant_id, nuevo_estado, current_user) → TareaResponse`
- `list_tareas(tenant_id, filtros) → list[TareaResponse]`
- `agregar_comentario(tarea_id, tenant_id, texto, current_user) → ComentarioResponse`
- `list_comentarios(tarea_id, tenant_id, current_user) → list[ComentarioResponse]`
- `get_tarea(tarea_id, tenant_id, current_user) → TareaResponse`

## New Capabilities

- `mis-tareas` — Vista self-scoped: TUTOR/PROFESOR/COORDINADOR ven tareas asignadas a ellos.
- `crear-tarea` — PROFESOR (en su contexto de materia) y COORDINADOR/ADMIN crean y asignan tareas.
- `cambiar-estado` — FSM Pendiente → En progreso → Resuelta / Cancelada.
- `admin-global` — Vista COORDINADOR/ADMIN: todas las tareas del tenant con filtros ricos.
- `comentarios` — Hilo asincrónico sobre cada tarea para asignado_a, asignado_por y gestores.

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Models | `app/models/tarea.py`, `app/models/comentario_tarea.py` | +2 |
| Migration | `alembic/versions/0NN_tarea_comentario_tarea.py` | +1 |
| Repositories | `app/repositories/tarea_repository.py`, `app/repositories/comentario_tarea_repository.py` | +2 |
| Service | `app/services/tarea_service.py` | +1 |
| Schemas | `app/schemas/tareas.py` | +1 |
| Router | `app/api/v1/routers/tareas.py` | +1 |
| main.py | Registrar router tareas | modify |
| Tests | `backend/tests/test_tareas.py` | +1 (~50 tests) |

No se toca `seed_permissions.py` — `tareas_internas:gestionar` ya está sembrado con los scopes correctos
(PROFESOR=own, COORDINADOR=all, ADMIN=all) desde C-04.

## Dependencies

- **C-07**: tablas `user`, `asignacion`, repo base, `get_current_user`, `require_permission`.
- **C-05**: helper `AuditService` (si se audita `TAREA_ASIGNAR`).
- C-16 **desbloquea**: C-23 (frontend-coordinacion, que consume estos endpoints).
