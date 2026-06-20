# Spec: Monitor Unificado (F2.7, F2.8, F2.9)

## Propósito

Vista filtrable del estado de actividades de los alumnos, con scope automático según el rol
de la sesión. Unifica F2.7 (coordinación/admin, global), F2.8 (tutor/profesor, propio) y
F2.9 (coordinación/admin, con rango de fechas) en un solo endpoint (D-C11-8).

---

## Endpoint

`GET /api/v1/analisis/monitor`

**Permiso**: `atrasados:ver` (scoped)

### Scope automático

El servicio resuelve el scope según la sesión (sin exponer la diferencia al cliente):

```
PROFESOR / TUTOR (scope=own)
  → filtra por los asignacion_id activos del usuario actual en el tenant
  → si tiene múltiples asignaciones (varias materias), las incluye todas a menos que
    materia_id esté especificado en los query params

COORDINADOR / ADMIN (scope=all)
  → no filtra por asignacion_id
  → puede filtrar por materia_id y cohorte_id si se especifican
```

### Query params

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `materia_id` | UUID | None | Filtro por materia (COORDINADOR/ADMIN: opcional; PROFESOR: ignorado si scope=own a menos que sea su materia) |
| `cohorte_id` | UUID | None | Filtro por cohorte |
| `alumno` | str | None | Búsqueda libre en `nombre` o `apellidos` (ILIKE %alumno%) |
| `comision` | str | None | Filtro exacto en `entradapadron.comision` |
| `regional` | str | None | Filtro exacto en `entradapadron.regional` |
| `estado` | str | None | `"atrasado"` \| `"al_dia"` — sin valor: retorna todos |
| `fecha_desde` | date | None | Filtra calificaciones con `importado_at >= fecha_desde` (F2.9) |
| `fecha_hasta` | date | None | Filtra calificaciones con `importado_at <= fecha_hasta` (F2.9) |
| `limit` | int | 100 | Max 500 |
| `offset` | int | 0 | Para paginación |

**Notas sobre filtros de fecha** (F2.9):
- `fecha_desde` / `fecha_hasta` aplican a `calificacion.importado_at`. Permiten al
  COORDINADOR/ADMIN acotar el análisis a un período de importación específico.
- Para PROFESOR/TUTOR estos filtros también aplican (restringen las calificaciones
  consideradas, no los alumnos mostrados).

### Query en `AnalisisRepository.monitor()`

El monitor es la query de atrasados (D-C11-3/D-C11-4) con los filtros opcionales
superpuestos sobre el CTE de `padron_activo`:

```sql
-- padron_activo con filtros aplicados
WITH padron_filtrado AS (
    SELECT ep.id, ep.nombre, ep.apellidos, ep.comision, ep.regional, vp.materia_id, vp.cohorte_id
    FROM entrada_padron ep
    JOIN version_padron vp ON ep.version_id = vp.id
    WHERE vp.tenant_id = :tenant_id
      AND vp.activa = TRUE AND vp.deleted_at IS NULL AND ep.deleted_at IS NULL
      -- Filtros opcionales:
      AND (:materia_id IS NULL OR vp.materia_id = :materia_id)
      AND (:cohorte_id IS NULL OR vp.cohorte_id = :cohorte_id)
      AND (:alumno IS NULL OR ep.nombre ILIKE :alumno_like OR ep.apellidos ILIKE :alumno_like)
      AND (:comision IS NULL OR ep.comision = :comision)
      AND (:regional IS NULL OR ep.regional = :regional)
      -- Scope own: solo asignaciones del usuario actual
      AND (:asignacion_ids IS NULL OR EXISTS (
          SELECT 1 FROM calificacion c
          WHERE c.entrada_padron_id = ep.id
            AND c.asignacion_id = ANY(:asignacion_ids)
            AND c.deleted_at IS NULL
      ))
),
...
-- Idéntico a la query de atrasados (CTEs actividades_scope, faltantes, bajo_umbral)
-- con la adición del filtro de fecha en calificacion:
--   AND (:fecha_desde IS NULL OR c.importado_at >= :fecha_desde)
--   AND (:fecha_hasta IS NULL OR c.importado_at <= :fecha_hasta)
```

Cuando `estado="atrasado"` se aplica la cláusula `WHERE f.ep_id IS NOT NULL OR b.ep_id IS NOT NULL`.
Cuando `estado="al_dia"` se aplica `WHERE f.ep_id IS NULL AND b.ep_id IS NULL`.

### Response (`MonitorResponse`)

```python
class MonitorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    regional: str | None
    materia_id: UUID          # incluido en el monitor para scope=all
    cohorte_id: UUID
    estado: str               # "atrasado" | "al_dia"
    actividades_faltantes: list[str]
    actividades_bajo_umbral: list[str]
    total_aprobadas: int
    total_calificaciones: int

class MonitorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MonitorItem]
    total: int        # total de alumnos en el resultado (sin paginación)
    limit: int
    offset: int
```

---

## Consideraciones de performance

- El monitor puede devolver N×M filas (alumnos × actividades en las listas).
  La paginación (limit/offset) aplica sobre los ALUMNOS, no sobre los ítems de las listas.
- El default de `limit=100` es suficiente para la mayoría de comisiones.
- Los índices de C-10 en `calificacion(tenant_id, materia_id, asignacion_id)` y
  `calificacion(tenant_id, materia_id, aprobado)` cubren las CTEs del monitor.
- Para scope=all con muchas materias, el query puede ser pesado. Se documenta en la UI
  (C-22/C-23) que el monitor de coordinación debería filtrar por materia o cohorte.

---

## Tests requeridos (en `test_analisis.py`)

| Test | Verifica |
|------|---------|
| `test_monitor_scope_own_solo_propios` | PROFESOR/TUTOR solo ven sus alumnos |
| `test_monitor_scope_all_todos` | COORDINADOR ve todos sin filtro |
| `test_monitor_filtro_alumno` | `alumno="García"` retorna solo alumnos que hacen match |
| `test_monitor_filtro_estado_atrasado` | `estado="atrasado"` retorna solo atrasados |
| `test_monitor_filtro_estado_al_dia` | `estado="al_dia"` retorna solo al día |
| `test_monitor_filtro_fecha_desde_hasta` | Fecha acota calificaciones consideradas |
| `test_monitor_paginacion` | `limit=2, offset=2` retorna el subset correcto |
| `test_monitor_rbac_403` | Sin `atrasados:ver` → 403 |
| `test_monitor_sin_datos` | Sin calificaciones → items=[], total=0 |
