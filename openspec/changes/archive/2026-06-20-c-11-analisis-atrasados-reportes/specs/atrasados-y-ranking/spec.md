# Spec: Atrasados y Ranking (F2.2, F2.3, F2.4, RN-06, RN-09)

## F2.2 — Alumnos atrasados

### Endpoint

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/atrasados`

**Permiso**: `atrasados:ver` (scoped)
**Scope automático**: PROFESOR/TUTOR → `asignacion_id` del usuario actual; COORDINADOR/ADMIN → todo el tenant.

### Query en `AnalisisRepository.atrasados()`

Ver D-C11-3 y D-C11-4 para las queries de faltantes y bajo-umbral.

**Algoritmo** (en SQL, ejecutado en AnalisisRepository):

```sql
-- Step 1: Set de actividades importadas para el scope
WITH actividades_scope AS (
    SELECT DISTINCT actividad FROM calificacion
    WHERE tenant_id = :tenant_id
      AND materia_id = :materia_id
      AND asignacion_id = :asignacion_id  -- NULL si scope=all (COORDINADOR)
      AND deleted_at IS NULL
),
-- Step 2: Alumnos del padrón activo
padron_activo AS (
    SELECT ep.id, ep.nombre, ep.apellidos, ep.email_hash, ep.comision, ep.regional
    FROM entrada_padron ep
    JOIN version_padron vp ON ep.version_id = vp.id
    WHERE vp.tenant_id = :tenant_id
      AND vp.materia_id = :materia_id
      AND vp.cohorte_id = :cohorte_id
      AND vp.activa = TRUE AND vp.deleted_at IS NULL
      AND ep.deleted_at IS NULL
),
-- Step 3: Actividades faltantes por alumno (D-C11-3)
faltantes AS (
    SELECT p.id as ep_id, STRING_AGG(a.actividad, '||') as actividades_faltantes
    FROM padron_activo p
    CROSS JOIN actividades_scope a
    WHERE NOT EXISTS (
        SELECT 1 FROM calificacion c
        WHERE c.entrada_padron_id = p.id
          AND c.actividad = a.actividad
          AND c.asignacion_id = :asignacion_id
          AND c.deleted_at IS NULL
    )
    GROUP BY p.id
),
-- Step 4: Actividades bajo umbral por alumno
bajo_umbral AS (
    SELECT c.entrada_padron_id AS ep_id, STRING_AGG(c.actividad, '||') AS actividades_bajo_umbral
    FROM calificacion c
    WHERE c.tenant_id = :tenant_id
      AND c.materia_id = :materia_id
      AND c.asignacion_id = :asignacion_id
      AND c.aprobado = FALSE
      AND c.deleted_at IS NULL
    GROUP BY c.entrada_padron_id
)
-- Step 5: Unión — alumnos con al menos una condición de atraso
SELECT p.id, p.nombre, p.apellidos, p.comision, p.regional,
       COALESCE(f.actividades_faltantes, '') AS faltantes_raw,
       COALESCE(b.actividades_bajo_umbral, '') AS bajo_umbral_raw
FROM padron_activo p
LEFT JOIN faltantes f ON f.ep_id = p.id
LEFT JOIN bajo_umbral b ON b.ep_id = p.id
WHERE f.ep_id IS NOT NULL OR b.ep_id IS NOT NULL
ORDER BY p.apellidos, p.nombre
```

El servicio divide los `_raw` por `||` para convertirlos en `list[str]`.

**Nota sobre scope=all (COORDINADOR/ADMIN)**: cuando `asignacion_id` es `None`, el repositorio
NO filtra por `asignacion_id` en las CTEs — usa solo `materia_id` y `cohorte_id`. Esto agrega
todas las calificaciones y finalizaciones del tenant para esa materia×cohorte.

### Response (`AtrasadosResponse`)

```python
class AlumnoAtrasado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    regional: str | None
    actividades_faltantes: list[str]
    actividades_bajo_umbral: list[str]

class AtrasadosResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_alumnos: int
    total_atrasados: int
    atrasados: list[AlumnoAtrasado]
```

### Sin datos

Si no hay calificaciones importadas para la materia×cohorte, retorna:
```json
{ "total_alumnos": 0, "total_atrasados": 0, "atrasados": [] }
```
HTTP 200. No es un error.

---

## F2.3 — Ranking de actividades aprobadas

### Endpoint

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/ranking`

**Permiso**: `atrasados:ver` (scoped, mismo scope que atrasados)

### Query en `AnalisisRepository.ranking()`

```sql
SELECT
    p.id AS entrada_padron_id,
    p.nombre, p.apellidos, p.comision,
    COUNT(c.id) FILTER (WHERE c.aprobado = TRUE)  AS total_aprobadas,
    COUNT(c.id)                                    AS total_calificaciones
FROM padron_activo p  -- igual que en atrasados
LEFT JOIN calificacion c ON c.entrada_padron_id = p.id
    AND c.materia_id = :materia_id
    AND c.asignacion_id = :asignacion_id   -- NULL si scope=all
    AND c.deleted_at IS NULL
GROUP BY p.id, p.nombre, p.apellidos, p.comision
HAVING COUNT(c.id) FILTER (WHERE c.aprobado = TRUE) > 0   -- RN-09: excluir 0 aprobadas
ORDER BY total_aprobadas DESC, p.apellidos, p.nombre
```

### Response (`RankingResponse`)

```python
class RankingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posicion: int                # 1-indexed
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    total_aprobadas: int
    total_calificaciones: int

class RankingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RankingItem]
    total_incluidos: int         # alumnos con ≥1 aprobada
    total_excluidos: int         # alumnos con 0 aprobadas (RN-09)
```

El servicio asigna `posicion` en Python (enumerate sobre la lista ordenada por el repo).

---

## F2.4 — Reporte rápido por materia

### Endpoint

`GET /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/reportes-rapidos`

**Permiso**: `atrasados:ver` (scoped)

### Query en `AnalisisRepository.reporte_rapido()`

Agrega métricas clave en una sola query:

```sql
SELECT
    COUNT(DISTINCT p.id)                                              AS total_alumnos,
    COUNT(DISTINCT c.actividad)                                       AS total_actividades,
    COUNT(DISTINCT c.id) FILTER (WHERE c.aprobado = TRUE)            AS total_aprobaciones,
    COUNT(DISTINCT c.id) FILTER (WHERE c.aprobado = FALSE)           AS total_desaprobaciones,
    COUNT(DISTINCT c.entrada_padron_id) FILTER (WHERE c.aprobado = FALSE) AS alumnos_con_desaprobacion,
    -- atrasados: al menos un aprobado=False o faltante (aproximado sin cross-join aquí)
    COUNT(DISTINCT ep_ids_atrasados.ep_id)                           AS alumnos_atrasados
FROM padron_activo p
LEFT JOIN calificacion c ON c.entrada_padron_id = p.id
    AND c.materia_id = :materia_id
    AND c.asignacion_id = :asignacion_id
    AND c.deleted_at IS NULL,
-- Subquery para el count de atrasados (usa el mismo CTE simplificado)
LATERAL (
    SELECT DISTINCT ep_id FROM (
        SELECT ep_id FROM faltantes UNION SELECT ep_id FROM bajo_umbral
    ) t
) ep_ids_atrasados
```

**Nota**: el `reporte_rapido` puede hacer dos queries (una para métricas básicas, otra para
el count de atrasados via la query de `atrasados()`). La simplicidad prima sobre la eficiencia
aquí, dado que esta vista se carga una vez y no en loops.

### Response (`ReporteRapidoResponse`)

```python
class ReporteRapidoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_alumnos: int
    total_actividades: int
    total_aprobaciones: int
    total_desaprobaciones: int
    alumnos_con_desaprobacion: int
    alumnos_atrasados: int
    tiene_datos: bool   # False si no hay calificaciones importadas
```

---

## Tests requeridos (en `test_analisis.py`)

| Test | Verifica |
|------|---------|
| `test_atrasados_bajo_umbral` | Alumno con nota < umbral aparece en bajo_umbral |
| `test_atrasados_faltante` | Alumno sin calificacion para actividad del set → faltante |
| `test_atrasados_al_dia` | Alumno con todas aprobadas → no aparece |
| `test_atrasados_vacio_sin_calificaciones` | Sin calificaciones importadas → lista vacía, 200 |
| `test_atrasados_scope_own` | PROFESOR ve solo sus propios alumnos |
| `test_atrasados_scope_all` | COORDINADOR ve todos los alumnos del tenant para la materia |
| `test_atrasados_rbac_403` | Sin permiso `atrasados:ver` → 403 |
| `test_ranking_excluye_cero_aprobadas` | Alumno con 0 aprobadas no aparece (RN-09) |
| `test_ranking_orden_descendente` | Más aprobadas primero |
| `test_ranking_posicion_1indexed` | Primer ítem tiene posicion=1 |
| `test_reporte_rapido_metricas` | Totales correctos con datos conocidos |
| `test_reporte_rapido_sin_datos` | `tiene_datos=False` si no hay calificaciones |
