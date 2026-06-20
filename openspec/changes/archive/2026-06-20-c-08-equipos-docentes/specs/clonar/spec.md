# Spec: clonar (F4.5, RN-12)

## Objetivo

`POST /api/v1/equipos/clonar` duplica todas las asignaciones vigentes de un equipo origen
`(materia_id × carrera_id × cohorte_id)` hacia un destino, con nuevas fechas de vigencia.
Feature estrella del setup de cuatrimestre (FL-03 paso 2).

## Guard

`require_permission("equipos:asignar")` — COORDINADOR/ADMIN.

## Request body

```json
{
  "origen": {
    "materia_id": "uuid | null",
    "carrera_id": "uuid | null",
    "cohorte_id": "uuid"
  },
  "destino": {
    "materia_id": "uuid | null",
    "carrera_id": "uuid | null",
    "cohorte_id": "uuid"
  },
  "desde": "2026-08-01",
  "hasta": "2026-12-31"
}
```

**Validaciones del schema**:
- Al menos `cohorte_id` o `materia_id` debe definirse en `origen` (no puede ser completamente vacío).
- `destino.cohorte_id` debe ser distinto de `origen.cohorte_id` (si son el mismo contexto exacto,
  no tiene sentido clonar).
- `desde` requerido; `hasta >= desde` si se proporciona.

## Response (201 Created)

```json
{
  "creados": 8,
  "omitidos": [
    {
      "usuario_id": "uuid",
      "motivo": "ya_vigente_en_destino"
    }
  ]
}
```

## Lógica del servicio (RN-12)

```python
async def clonar_equipo(tenant_id: UUID, payload: ClonarEquipoRequest)
    → ClonarResult:

    # 1. Validar FKs del origen y destino en el tenant
    await _validar_contexto(tenant_id, payload.origen)
    await _validar_contexto(tenant_id, payload.destino)

    # 2. Cargar asignaciones vigentes del origen
    hoy = date.today()
    vigentes = await repo.list_vigentes_por_contexto(
        tenant_id,
        materia_id=payload.origen.materia_id,
        carrera_id=payload.origen.carrera_id,
        cohorte_id=payload.origen.cohorte_id,
        hoy=hoy,
    )
    # vigentes: solo rows donde deleted_at IS NULL Y compute_vigencia=Vigente

    # 3. Para cada vigente, verificar si ya existe en destino
    creadas, omitidas = [], []
    async with session.begin():
        for a in vigentes:
            ya_existe = await repo.existe_vigente_en_destino(
                tenant_id,
                usuario_id=a.usuario_id,
                rol_id=a.rol_id,
                materia_id=payload.destino.materia_id,
                carrera_id=payload.destino.carrera_id,
                cohorte_id=payload.destino.cohorte_id,
                hoy=hoy,
            )
            if ya_existe:
                omitidas.append({"usuario_id": str(a.usuario_id), "motivo": "ya_vigente_en_destino"})
                continue

            nueva = Asignacion(
                tenant_id=tenant_id,
                usuario_id=a.usuario_id,
                rol_id=a.rol_id,
                materia_id=payload.destino.materia_id,
                carrera_id=payload.destino.carrera_id,
                cohorte_id=payload.destino.cohorte_id,
                comisiones=a.comisiones,
                responsable_id=a.responsable_id,
                desde=payload.desde,
                hasta=payload.hasta,
            )
            session.add(nueva)
            creadas.append(nueva)

    # 4. Audit
    await audit.registrar(
        accion="ASIGNACION_MODIFICAR",
        filas_afectadas=len(creadas),
        detalle={
            "operacion": "clonar",
            "origen": {...},
            "destino": {...},
            "desde": str(payload.desde),
            "hasta": str(payload.hasta) if payload.hasta else None,
            "omitidos": len(omitidas),
        }
    )

    return ClonarResult(creados=len(creadas), omitidos=omitidas)
```

## Edge cases

| Caso | Comportamiento |
|------|----------------|
| Origen sin asignaciones vigentes | Devuelve `{ "creados": 0, "omitidos": [] }` — HTTP 201 |
| Todos ya existen en destino | Devuelve `{ "creados": 0, "omitidos": [N entradas] }` — HTTP 201 |
| cohorte_id destino no existe | 404 con mensaje descriptivo |
| FK inválido en origen/destino | 404 con campo que falla |
| `hasta < desde` | 400 |

## Criterios de aceptación

- [ ] Copia solo asignaciones Vigentes del origen (las vencidas no se clonan).
- [ ] Las filas nuevas tienen `cohorte_id` del destino y las fechas del payload.
- [ ] `responsable_id` y `comisiones` se copian del origen.
- [ ] Asignaciones ya vigentes en el destino se omiten (no falla el request).
- [ ] Transaccional: rollback si falla cualquier INSERT.
- [ ] 404 si FK del destino no existe en el tenant.
- [ ] 400 si `hasta < desde`.
- [ ] Audit `ASIGNACION_MODIFICAR` con `filas_afectadas` = N creadas.

## Tests

- `test_clonar_equipo_exitoso`: origen con 5 vigentes → 5 creadas en destino.
- `test_clonar_origen_sin_vigentes`: origen vacío → `{ "creados": 0 }`, 201.
- `test_clonar_omite_ya_existentes`: 2 de 5 ya vigentes en destino → `creados: 3, omitidos: 2`.
- `test_clonar_no_copia_vencidas`: asignación vencida en origen no se clona.
- `test_clonar_cohorte_destino_invalido_404`: cohorte_id destino no existe → 404.
- `test_clonar_hasta_menor_que_desde_400`: fecha inválida → 400.
- `test_clonar_registra_audit`: audit con filas_afectadas y detalle de origen/destino.
- `test_clonar_sin_permiso_403`: sin `equipos:asignar` → 403.
