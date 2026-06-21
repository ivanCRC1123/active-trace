# Spec: asignar-tarea (F8.2 — crear, estado propio)

## Objetivo

Cubrir F8.2: crear y asignar tareas a otros docentes (trazabilidad asignador/asignado) y
cambiar el estado de tareas (FSM). Incluye la verificación de scope "own" del PROFESOR.

---

## POST /api/v1/tareas — Crear tarea

### Guard

`require_permission("tareas_internas:gestionar")`

PROFESOR: scope=`own` → el service verifica contexto de materia.
COORDINADOR / ADMIN: scope=`all` → sin restricción adicional.

### Request body

```json
{
  "asignado_a": "uuid",
  "descripcion": "Revisar avances de la comisión B antes del viernes",
  "materia_id": "uuid | null",
  "contexto_id": "uuid | null"
}
```

`asignado_por` NO es parte del request body — el service lo fija como `current_user.id`.

### Validaciones en el service

1. `asignado_a` debe existir en el tenant (usuario activo, `deleted_at IS NULL`). Si no → 422.
2. Si `materia_id` no es null → debe existir y pertenecer al tenant. Si no → 422.
3. Si el usuario tiene scope=`own` (PROFESOR):
   - Si `materia_id` es null → 403 (`PROFESOR requiere materia para crear tareas`).
   - Si `materia_id` no es null → verificar que el PROFESOR tenga asignación vigente a esa materia.
     Si no → 403.
4. `estado` inicial siempre = `"Pendiente"`. No editable en creación.

### Response

HTTP 201 con `TareaResponse` (mismo schema de mis-tareas).

### Auditoría

`AuditService.log(accion="TAREA_ASIGNAR", detalle={tarea_id, asignado_a, materia_id, estado_inicial="Pendiente"}, filas=1)`

### Criterios de aceptación — POST

- [ ] `asignado_por` = `current_user.id` (JWT), no del body.
- [ ] `estado` inicial = `Pendiente`.
- [ ] PROFESOR sin asignación vigente a la materia → 403.
- [ ] PROFESOR con `materia_id=null` → 403.
- [ ] COORDINADOR con `materia_id=null` → 201 (tarea institucional).
- [ ] `asignado_a` de otro tenant → 422.
- [ ] Sin `tareas_internas:gestionar` → 403.
- [ ] Audit `TAREA_ASIGNAR` generado.
- [ ] `contexto_id` almacenado aunque el UUID no apunte a ninguna entidad real.

### Tests — POST

- `test_crear_tarea_coordinador_sin_materia`: COORDINADOR crea tarea institucional → 201.
- `test_crear_tarea_coordinador_con_materia`: COORDINADOR + materia válida → 201.
- `test_crear_tarea_profesor_propia_materia`: PROFESOR con asignación vigente → 201.
- `test_crear_tarea_profesor_materia_ajena_403`: PROFESOR + materia donde no tiene asignación → 403.
- `test_crear_tarea_profesor_sin_materia_403`: PROFESOR + materia_id=null → 403.
- `test_crear_tarea_asignado_a_otro_tenant_422`: asignado_a de otro tenant → 422.
- `test_crear_tarea_sin_permiso_403`: TUTOR sin gestionar → 403.
- `test_crear_tarea_registra_audit`: audit TAREA_ASIGNAR presente.
- `test_crear_tarea_contexto_id_opaco`: contexto_id con UUID random → 201 sin error.

---

## PATCH /api/v1/tareas/{id}/estado — Cambiar estado FSM

### Guard

Identity + ownership check (sin `require_permission` propio). El service implementa:

```python
def _puede_cambiar_estado(current_user, tarea, tiene_gestionar_perm) -> bool:
    return (
        current_user.id == tarea.asignado_a
        or current_user.id == tarea.asignado_por
        or tiene_gestionar_perm
    )
```

Si ninguna condición → 403.

### Request body

```json
{ "estado": "En progreso" }
```

### FSM — transiciones válidas

| Desde | Hacia | Quién |
|-------|-------|-------|
| Pendiente | En progreso | `asignado_a`, gestores |
| Pendiente | Cancelada | `asignado_por`, gestores |
| En progreso | Resuelta | `asignado_a`, gestores |
| En progreso | Cancelada | gestores únicamente |
| Resuelta | * | ninguno (terminal) |
| Cancelada | * | ninguno (terminal) |

Transición inválida → 422 con mensaje descriptivo (`TAREA_TRANSICION_INVALIDA`).
Estado terminal → 422 con `TAREA_ESTADO_TERMINAL`.

### Response

HTTP 200 con `TareaResponse` actualizado.

### Auditoría

`AuditService.log(accion="TAREA_ESTADO_CAMBIAR", detalle={tarea_id, estado_anterior, estado_nuevo}, filas=1)`

### Criterios de aceptación — PATCH estado

- [ ] Pendiente → En progreso por `asignado_a` → 200.
- [ ] Pendiente → Cancelada por `asignado_por` → 200.
- [ ] En progreso → Resuelta por `asignado_a` → 200.
- [ ] En progreso → Cancelada por `asignado_por` solo → 403 (solo gestores pueden cancelar en-progreso).
- [ ] Resuelta → cualquier cosa → 422 (`TAREA_ESTADO_TERMINAL`).
- [ ] Transición no válida → 422 (`TAREA_TRANSICION_INVALIDA`).
- [ ] Usuario ajeno (ni asignado_a, ni asignado_por, ni gestor) → 403.
- [ ] TUTOR como `asignado_a` puede cambiar a En progreso → 200.
- [ ] Tarea de otro tenant → 404.
- [ ] Audit `TAREA_ESTADO_CAMBIAR` generado.

### Tests — PATCH estado

- `test_estado_pendiente_en_progreso_asignado_a_200`.
- `test_estado_pendiente_cancelada_asignado_por_200`.
- `test_estado_en_progreso_resuelta_asignado_a_200`.
- `test_estado_en_progreso_cancelada_asignado_por_403`.
- `test_estado_en_progreso_cancelada_coordinador_200`.
- `test_estado_resuelta_cualquiera_422_terminal`.
- `test_estado_cancelada_cualquiera_422_terminal`.
- `test_estado_transicion_invalida_422`.
- `test_estado_tutor_asignado_puede_iniciar`.
- `test_estado_usuario_ajeno_403`.
- `test_estado_otro_tenant_404`.
- `test_estado_registra_audit`.

---

## GET /api/v1/tareas/{id} — Detalle de tarea

### Guard

Identity + membership check (sin `require_permission`):
- `current_user.id == tarea.asignado_a` OR
- `current_user.id == tarea.asignado_por` OR
- Tiene `tareas_internas:gestionar`

### Response

HTTP 200 con `TareaResponse` completo incluyendo `TareaFiltros` resueltos.

### Tests

- `test_detalle_asignado_a_200`.
- `test_detalle_asignado_por_200`.
- `test_detalle_gestor_200`.
- `test_detalle_usuario_ajeno_403`.
- `test_detalle_otro_tenant_404`.
