# Spec: mis-equipos (F4.2)

## Objetivo

`GET /api/v1/equipos/mis-equipos` devuelve las asignaciones del usuario autenticado
dentro de su tenant, con filtros opcionales. Es la vista personal del docente.

## Guard

`require_permission("equipos:ver")` — scope=own (el service filtra por `usuario_id` del JWT).

## Quién puede acceder

PROFESOR, TUTOR, NEXO, COORDINADOR, ADMIN. El scope es siempre propio: solo se devuelven
las asignaciones del usuario cuyo id aparece en el JWT verificado.

## Query params

| Param | Tipo | Descripción |
|-------|------|-------------|
| `materia_id` | UUID (opt) | Filtrar por materia |
| `carrera_id` | UUID (opt) | Filtrar por carrera |
| `cohorte_id` | UUID (opt) | Filtrar por cohorte |
| `rol` | str (opt) | Nombre del rol (ej: "PROFESOR") |
| `estado_vigencia` | `"Vigente"` \| `"Vencida"` (opt) | Filtrar por vigencia actual |

## Response

```json
[
  {
    "id": "uuid",
    "usuario_id": "uuid",
    "rol": "PROFESOR",
    "materia_id": "uuid",
    "materia_nombre": "Programación I",
    "carrera_id": "uuid",
    "carrera_nombre": "TUPAD",
    "cohorte_id": "uuid",
    "cohorte_nombre": "MAR-2026",
    "comisiones": ["MAT_A"],
    "responsable_id": "uuid | null",
    "desde": "2026-03-01",
    "hasta": "2026-07-31",
    "estado_vigencia": "Vigente"
  }
]
```

HTTP 200 con lista vacía si no hay asignaciones que cumplan los filtros.

## Lógica del servicio

```python
async def mis_equipos(usuario_id: UUID, tenant_id: UUID, filtros: MisEquiposFiltros)
    → list[AsignacionEquipoResponse]:
    rows = await repo.list_by_usuario(usuario_id, tenant_id, filtros)
    return [_to_response(r) for r in rows]
```

`_to_response` computa `estado_vigencia` via `compute_estado_vigencia(desde, hasta)` (ya
implementado en C-07). Los nombres de materia/carrera/cohorte se resuelven con un join en el
repositorio.

## Criterios de aceptación

- [ ] Solo devuelve asignaciones del usuario del JWT (sin query param `usuario_id`).
- [ ] Filtros opcionales funcionan de forma combinada (AND).
- [ ] Incluye `estado_vigencia` calculado.
- [ ] `404` si el tenant del JWT no existe (guarda base de C-02).
- [ ] Sin `deleted_at IS NOT NULL` en la respuesta.
- [ ] HTTP 200 con `[]` si no hay resultado.

## Tests

- `test_mis_equipos_devuelve_propias`: usuario A ve sus asignaciones, no las de B.
- `test_mis_equipos_filtro_materia`: filtra por materia_id correctamente.
- `test_mis_equipos_filtro_vigencia`: `estado_vigencia=Vigente` excluye vencidas.
- `test_mis_equipos_sin_permiso_403`: sin `equipos:ver` → 403.
- `test_mis_equipos_cross_tenant_vacio`: usuario de otro tenant → lista vacía (isolation).
