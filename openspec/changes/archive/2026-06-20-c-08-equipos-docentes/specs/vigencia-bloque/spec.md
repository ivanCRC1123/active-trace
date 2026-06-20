# Spec: vigencia-bloque (F4.6)

## Objetivo

`PATCH /api/v1/equipos/vigencia` actualiza `desde` y `hasta` de todas las asignaciones
activas de un equipo identificado por contexto `(materia_id × carrera_id × cohorte_id)`.
Permite ajustar el período de vigencia del equipo completo sin tocar cada fila individualmente.

## Guard

`require_permission("equipos:asignar")` — COORDINADOR/ADMIN.

## Request body

```json
{
  "materia_id": "uuid | null",
  "carrera_id": "uuid | null",
  "cohorte_id": "uuid | null",
  "desde": "2026-03-01",
  "hasta": "2026-07-31"
}
```

**Validaciones del schema**:
- Al menos uno de `materia_id`, `carrera_id`, `cohorte_id` debe ser no-null (contexto mínimo).
- `desde` requerido.
- `hasta` >= `desde` si se proporciona.

## Response (200 OK)

```json
{
  "filas_afectadas": 7
}
```

`filas_afectadas: 0` es válido — devuelve 200 (no hay asignaciones en ese contexto).

## Lógica del servicio

```python
async def actualizar_vigencia_bloque(
    tenant_id: UUID, payload: VigenciaBloqueRequest
) → int:

    # UPDATE en bulk — repositorio hace:
    # UPDATE asignacion
    #    SET desde = :desde, hasta = :hasta, updated_at = now()
    #  WHERE tenant_id = :t
    #    AND deleted_at IS NULL
    #    AND (materia_id = :m OR :m IS NULL)
    #    AND (carrera_id = :c OR :c IS NULL)
    #    AND (cohorte_id = :co OR :co IS NULL)
    # RETURNING id  -- para contar filas

    filas = await repo.bulk_update_vigencia(
        tenant_id,
        materia_id=payload.materia_id,
        carrera_id=payload.carrera_id,
        cohorte_id=payload.cohorte_id,
        desde=payload.desde,
        hasta=payload.hasta,
    )

    await audit.registrar(
        accion="ASIGNACION_MODIFICAR",
        filas_afectadas=filas,
        detalle={
            "operacion": "vigencia_bloque",
            "contexto": {
                "materia_id": str(payload.materia_id) if payload.materia_id else None,
                "carrera_id": str(payload.carrera_id) if payload.carrera_id else None,
                "cohorte_id": str(payload.cohorte_id) if payload.cohorte_id else None,
            },
            "desde": str(payload.desde),
            "hasta": str(payload.hasta) if payload.hasta else None,
        }
    )
    return filas
```

**Importante**: el filtro `NULL` es optativo. Si se pasa solo `cohorte_id`, actualiza TODAS
las asignaciones de esa cohorte (sin importar materia ni carrera). Esto permite actualizar el
cuatrimestre completo en una sola operación.

## Criterios de aceptación

- [ ] Actualiza `desde` y `hasta` de todas las filas con `deleted_at IS NULL` que coincidan con el contexto.
- [ ] Devuelve el número exacto de filas afectadas.
- [ ] `filas_afectadas: 0` → 200 OK (no es error).
- [ ] 400 si `hasta < desde`.
- [ ] 400 si todos los FKs de contexto son null (contexto vacío no aceptado).
- [ ] Audit `ASIGNACION_MODIFICAR` con `filas_afectadas` correcto.
- [ ] Aislamiento de tenant: nunca modifica asignaciones de otro tenant.

## Tests

- `test_vigencia_bloque_actualiza_cohorte`: 5 asignaciones de la cohorte → todas actualizadas, 200.
- `test_vigencia_bloque_filtro_materia`: solo las asignaciones de esa materia se actualizan.
- `test_vigencia_bloque_sin_matches`: contexto sin asignaciones → `{"filas_afectadas": 0}`, 200.
- `test_vigencia_bloque_hasta_menor_que_desde_400`: fecha inválida → 400.
- `test_vigencia_bloque_contexto_vacio_400`: todos los FKs null → 400.
- `test_vigencia_bloque_registra_audit`: audit log con filas_afectadas.
- `test_vigencia_bloque_sin_permiso_403`: sin `equipos:asignar` → 403.
