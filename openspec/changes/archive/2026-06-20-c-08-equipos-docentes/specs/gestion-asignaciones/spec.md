# Spec: gestion-asignaciones (F4.3)

## Objetivo

`GET /api/v1/equipos` lista todas las asignaciones del tenant con filtros ricos.
Es la vista de gestión del COORDINADOR/ADMIN (F4.3).

## Guard

`require_permission("equipos:asignar")` — COORDINADOR scope=all, ADMIN scope=all.

## Query params

| Param | Tipo | Descripción |
|-------|------|-------------|
| `materia_id` | UUID (opt) | FK → Materia |
| `carrera_id` | UUID (opt) | FK → Carrera |
| `cohorte_id` | UUID (opt) | FK → Cohorte |
| `usuario_id` | UUID (opt) | FK → Usuario |
| `rol` | str (opt) | Nombre del rol |
| `responsable_id` | UUID (opt) | FK → Usuario (jerarquía) |
| `estado_vigencia` | `"Vigente"` \| `"Vencida"` (opt) | Filtrar por vigencia |
| `limit` | int (opt, default 100, max 500) | Paginación |
| `offset` | int (opt, default 0) | Paginación |

## Response

Misma estructura que `mis-equipos` pero incluye datos del usuario en cada fila:

```json
[
  {
    "id": "uuid",
    "usuario_id": "uuid",
    "usuario_nombre": "María",
    "usuario_apellidos": "García",
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

HTTP 200. Lista vacía si no hay resultados.

## Diferencia con `/asignaciones` (C-07)

- `/asignaciones`: CRUD básico, menos filtros, sin join de nombres.
- `/equipos`: vista de dominio con nombre legible de cada FK y filtros orientados al negocio.

## Criterios de aceptación

- [ ] Filtros combinados (todos los params son AND entre sí).
- [ ] Paginación funciona (`limit`, `offset`).
- [ ] `estado_vigencia` calculado por el service.
- [ ] Nombres resueltos via join (no IDs crudos únicamente).
- [ ] Aislamiento de tenant: nunca devuelve asignaciones de otro tenant.
- [ ] Sin `deleted_at IS NOT NULL`.

## Tests

- `test_list_equipo_todos`: devuelve todas las asignaciones del tenant.
- `test_list_equipo_filtro_cohorte`: filtra correctamente por `cohorte_id`.
- `test_list_equipo_filtro_vigencia`: excluye vencidas cuando `estado_vigencia=Vigente`.
- `test_list_equipo_paginacion`: `offset` y `limit` funcionan.
- `test_list_equipo_sin_permiso_403`: sin `equipos:asignar` → 403.
