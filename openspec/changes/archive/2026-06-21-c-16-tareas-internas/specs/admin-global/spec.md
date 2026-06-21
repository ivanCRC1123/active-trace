# Spec: admin-global (F8.3 — vista global con filtros)

## Objetivo

`GET /api/v1/tareas` expone la vista administrativa de todas las tareas del tenant con
filtros ricos (F8.3). Exclusiva de roles con `tareas_internas:gestionar all`.

## Guard

`require_permission("tareas_internas:gestionar")`

COORDINADOR / ADMIN (scope=`all`) → ven todas las tareas del tenant.
PROFESOR (scope=`own`) → el service aplica filtro automático:
`(asignado_por == current_user.id OR asignado_a == current_user.id)`.
El PROFESOR no puede ver tareas donde no es parte (ver D-C16-5 en design.md).

## Query params

| Param | Tipo | Descripción |
|-------|------|-------------|
| `asignado_a` | UUID (opt) | FK → Usuario |
| `asignado_por` | UUID (opt) | FK → Usuario |
| `materia_id` | UUID (opt) | FK → Materia |
| `estado` | str (opt) | `Pendiente`, `En progreso`, `Resuelta`, `Cancelada` |
| `q` | str (opt) | Búsqueda libre sobre `descripcion` (ILIKE `%q%`) |
| `limit` | int (opt, default 50, max 200) | Paginación |
| `offset` | int (opt, default 0) | Paginación |

Todos los filtros son opcionales y se combinan con AND.

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
    "estado": "En progreso",
    "descripcion": "Revisar avances de la comisión B",
    "contexto_id": "uuid | null",
    "created_at": "2026-06-21T10:00:00Z",
    "updated_at": "2026-06-21T12:30:00Z"
  }
]
```

HTTP 200 con lista vacía si no hay resultados que cumplan los filtros.
Los nombres se resuelven via join — nunca se expone email.

## Lógica del servicio

```python
async def list_tareas(
    tenant_id: UUID,
    filtros: TareaFiltros,
    current_user: CurrentUser,
    scope: str,  # 'own' | 'all'
) -> list[TareaResponse]:
    if scope == "own":
        # PROFESOR: inyectar filtro de membresía invisible al caller
        filtros = filtros.model_copy(
            update={"_scope_user_id": current_user.id}
        )
    rows = await repo.list_tareas(tenant_id, filtros)
    return [_to_response(r) for r in rows]
```

El repositorio traduce `_scope_user_id` a:
```sql
AND (asignado_por = :uid OR asignado_a = :uid)
```

## Criterios de aceptación

- [ ] COORDINADOR sin filtros → todas las tareas del tenant.
- [ ] Filtros `asignado_a`, `asignado_por`, `materia_id`, `estado` funcionan en combinación.
- [ ] Búsqueda libre `q` hace ILIKE sobre `descripcion`.
- [ ] Paginación `limit`/`offset` operativa.
- [ ] PROFESOR con scope=own → solo tareas donde es parte (asignado_a OR asignado_por).
- [ ] PROFESOR no puede ver tareas ajenas incluso sin filtros.
- [ ] TUTOR sin permiso → 403.
- [ ] Aislamiento de tenant: nunca devuelve tareas de otro tenant.
- [ ] Sin `deleted_at IS NOT NULL` en la respuesta.

## Tests

- `test_admin_global_coordinador_ve_todo`: COORDINADOR sin filtros → todas las tareas del tenant.
- `test_admin_global_filtro_asignado_a`: filtra correctamente.
- `test_admin_global_filtro_asignado_por`: filtra correctamente.
- `test_admin_global_filtro_materia`: filtra por materia_id.
- `test_admin_global_filtro_estado`: solo estado=Pendiente.
- `test_admin_global_busqueda_libre`: `q=comision` encuentra tarea con esa palabra.
- `test_admin_global_paginacion`: limit=2, offset=2 → página 2.
- `test_admin_global_profesor_scope_own`: PROFESOR solo ve sus tareas.
- `test_admin_global_profesor_no_ve_ajenas`: tarea sin PROFESOR como parte → invisible.
- `test_admin_global_tutor_403`: TUTOR → 403 (sin permiso).
- `test_admin_global_cross_tenant`: tarea de tenant B invisible para COORDINADOR de tenant A.
- `test_admin_global_excluye_soft_deleted`: tarea con deleted_at no aparece.
