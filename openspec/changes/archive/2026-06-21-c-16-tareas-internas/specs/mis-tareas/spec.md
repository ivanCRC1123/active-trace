# Spec: mis-tareas (F8.1)

## Objetivo

`GET /api/v1/tareas/mis-tareas` devuelve las tareas donde `asignado_a == current_user.id`
dentro del tenant. Es la vista personal del docente (F8.1).

## Guard

Solo `get_current_user` — **sin** `require_permission`. Disponible para cualquier usuario
autenticado, incluyendo TUTOR (que no tiene `tareas_internas:gestionar`).

Ver D-C16-1 en design.md para la justificación completa.

## Quién puede acceder

Cualquier usuario autenticado (TUTOR, PROFESOR, COORDINADOR, ADMIN, etc.). El scope es
siempre `asignado_a == current_user.id` — el usuario solo ve sus propias tareas.

## Query params

| Param | Tipo | Descripción |
|-------|------|-------------|
| `estado` | str (opt) | `Pendiente`, `En progreso`, `Resuelta`, `Cancelada` |
| `materia_id` | UUID (opt) | Filtrar por materia |
| `limit` | int (opt, default 50, max 200) | Paginación |
| `offset` | int (opt, default 0) | Paginación |

## Response

```json
[
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "materia_id": "uuid | null",
    "asignado_a": {
      "id": "uuid",
      "nombre": "María",
      "apellidos": "García"
    },
    "asignado_por": {
      "id": "uuid",
      "nombre": "Carlos",
      "apellidos": "Pérez"
    },
    "estado": "Pendiente",
    "descripcion": "Revisar avances de la comisión B",
    "contexto_id": "uuid | null",
    "created_at": "2026-06-21T10:00:00Z",
    "updated_at": "2026-06-21T10:00:00Z"
  }
]
```

HTTP 200 con lista vacía si no hay tareas. Los campos `nombre` y `apellidos` se resuelven
vía join en el repositorio — nunca se expone email.

## Lógica del servicio

```python
async def mis_tareas(
    usuario_id: UUID,
    tenant_id: UUID,
    filtros: MisTareasFiltros,
) -> list[TareaResponse]:
    rows = await repo.list_by_asignado_a(usuario_id, tenant_id, filtros)
    return [_to_response(r) for r in rows]
```

El repositorio hace join con `user` (alias `u_a` para asignado_a, `u_p` para asignado_por)
para resolver nombres. Excluye `deleted_at IS NOT NULL`.

## Criterios de aceptación

- [ ] Solo devuelve tareas donde `asignado_a == current_user.id` del JWT.
- [ ] No acepta `?asignado_a=` como query param para suplantación.
- [ ] Filtros opcionales funcionan en combinación (AND).
- [ ] Paginación `limit`/`offset` operativa.
- [ ] Nombres resueltos (`asignado_a.nombre`, `asignado_por.nombre`), sin emails.
- [ ] HTTP 200 con `[]` si no hay resultados.
- [ ] Sin `deleted_at IS NOT NULL` en la respuesta.
- [ ] Aislamiento: usuario de tenant B no ve tareas de tenant A.
- [ ] TUTOR sin ningún permiso adicional puede acceder: HTTP 200, no 403.

## Tests

- `test_mis_tareas_devuelve_propias`: usuario A (TUTOR) ve sus tareas, no las de B.
- `test_mis_tareas_tutor_sin_permiso_accede`: TUTOR sin `tareas_internas:gestionar` → 200.
- `test_mis_tareas_filtro_estado`: `estado=Pendiente` excluye Resueltas.
- `test_mis_tareas_filtro_materia`: filtra por materia_id.
- `test_mis_tareas_paginacion`: limit/offset funcionan.
- `test_mis_tareas_cross_tenant_vacio`: usuario de otro tenant → lista vacía.
- `test_mis_tareas_sin_auth_401`: sin Bearer → 401.
- `test_mis_tareas_excluye_soft_deleted`: tarea con deleted_at → no aparece.
