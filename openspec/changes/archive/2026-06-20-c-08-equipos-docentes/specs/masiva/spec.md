# Spec: masiva (F4.4)

## Objetivo

`POST /api/v1/equipos/masiva` crea en una sola operación N asignaciones para el mismo
contexto `(materia × carrera × cohorte × rol)` con una vigencia uniforme (F4.4, RN-30).

## Guard

`require_permission("equipos:asignar")` — COORDINADOR/ADMIN.

## Request body

```json
{
  "usuario_ids": ["uuid1", "uuid2", "uuid3"],
  "rol_id": "uuid",
  "materia_id": "uuid | null",
  "carrera_id": "uuid | null",
  "cohorte_id": "uuid | null",
  "comisiones": [],
  "responsable_id": "uuid | null",
  "desde": "2026-03-01",
  "hasta": "2026-07-31"
}
```

Pydantic schema con `extra='forbid'`.

**Validaciones del schema**:
- `usuario_ids`: lista no vacía (min 1 elemento).
- `desde` requerido.
- `hasta` >= `desde` si se proporciona.

## Response (201 Created)

```json
{
  "creados": 3,
  "asignaciones": ["uuid1", "uuid2", "uuid3"]
}
```

## Lógica del servicio — dos pasadas

**Pasada 1 — Validación**:
1. Verificar que todos los `usuario_ids` existen en el tenant (`deleted_at IS NULL`, `is_active=True`).
2. Verificar `rol_id` válido en el tenant.
3. Verificar FKs opcionales (`materia_id`, `carrera_id`, `cohorte_id`) en el tenant.
4. Verificar que ningún `usuario_id` tenga ya una asignación vigente al mismo `(rol_id, materia_id,
   carrera_id, cohorte_id)` en el tenant. Si existe → incluir en lista de conflictos → 422.

Si cualquier validación falla → `422 Unprocessable Entity` con detalle:
```json
{
  "detail": "validación fallida",
  "usuario_ids_invalidos": ["uuid-x"],
  "usuario_ids_duplicados": ["uuid-y"]
}
```
No se inserta nada.

**Pasada 2 — Inserción (solo si validación completa OK)**:
```python
async with session.begin():
    for uid in payload.usuario_ids:
        asignacion = Asignacion(
            tenant_id=tenant_id,
            usuario_id=uid,
            rol_id=payload.rol_id,
            materia_id=payload.materia_id,
            ...
        )
        session.add(asignacion)
```

**Audit**: `ASIGNACION_MODIFICAR` con `filas_afectadas=len(usuario_ids)`, `detalle={"operacion": "masiva", "rol_id": ..., "contexto": {...}}`.

## Criterios de aceptación

- [ ] Inserta exactamente N asignaciones cuando todos los user_ids son válidos.
- [ ] 422 si algún `usuario_id` no existe en el tenant.
- [ ] 422 si algún `usuario_id` ya tiene una asignación vigente en el mismo contexto.
- [ ] 400 si `hasta < desde`.
- [ ] Transaccional: si falla la inserción de uno → rollback de todos.
- [ ] Audit `ASIGNACION_MODIFICAR` con `filas_afectadas` correcto.
- [ ] Aislamiento de tenant: no puede referenciar usuarios de otro tenant.

## Tests

- `test_masiva_crea_N_asignaciones`: 3 user_ids válidos → 3 asignaciones, 201.
- `test_masiva_usuario_invalido_422`: un user_id que no existe en el tenant → 422, ninguna fila insertada.
- `test_masiva_duplicado_422`: user_id ya vigente en ese contexto → 422.
- `test_masiva_hasta_menor_que_desde_400`: fecha inválida → 400.
- `test_masiva_sin_permiso_403`: sin `equipos:asignar` → 403.
- `test_masiva_registra_audit`: audit log registrado con filas_afectadas=N.
