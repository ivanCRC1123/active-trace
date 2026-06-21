# Spec — Panel de Interacciones (F9.1)

> Read-only sobre `audit_log` (C-05) y `comunicacion` (C-12). Sin migración.

---

## Sub-vistas

### F9.1(a) — Acciones por día

**Endpoint**: `GET /api/v1/auditoria/panel/acciones-por-dia`

**Query params**:
```
from_date : date (YYYY-MM-DD) — opcional
to_date   : date (YYYY-MM-DD) — opcional
materia_id: UUID              — opcional (ignorado si scope=own, se usa el set de materias propias)
```

**Query SQL equivalente**:
```sql
SELECT DATE(fecha_hora AT TIME ZONE 'UTC') AS fecha, COUNT(*) AS cantidad
FROM audit_log
WHERE tenant_id = :tenant_id
  [AND fecha_hora >= :from_date]
  [AND fecha_hora <= :to_date + interval '1 day']
  [AND materia_id IN (:materias)]   -- scope=own: set calculado; scope=all + filtro: materia_id param
GROUP BY 1
ORDER BY 1 ASC
```

**Response schema**:
```python
class AccionXDia(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fecha: date
    cantidad: int

class AccionesXDiaResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[AccionXDia]
    total_acciones: int  # sum(cantidad)
```

**Comportamiento**:
- Días sin actividad no aparecen (no hay relleno de ceros).
- Si el rango es vacío o el set de materias propias es vacío: `items=[], total_acciones=0`.

---

### F9.1(b) — Estado de comunicaciones por docente

**Endpoint**: `GET /api/v1/auditoria/panel/comunicaciones-docente`

**Query params**:
```
materia_id: UUID — opcional
```

**Query SQL equivalente**:
```sql
SELECT c.enviado_por, c.estado, COUNT(*) AS cantidad
FROM comunicacion c
WHERE c.tenant_id = :tenant_id
  AND c.deleted_at IS NULL
  [AND c.materia_id IN (:materias)]   -- scope=own
  [AND c.materia_id = :materia_id]    -- filtro explícito (scope=all)
GROUP BY c.enviado_por, c.estado
```

El service resuelve el nombre del docente:
```sql
SELECT id, nombre, apellidos FROM "user"
WHERE id IN (:set_enviado_por) AND tenant_id = :tenant_id AND deleted_at IS NULL
```

**Response schema**:
```python
class EstadoComunicacionXDocente(BaseModel):
    model_config = ConfigDict(extra='forbid')
    actor_id: UUID
    nombre: str
    apellidos: str
    # email NO se incluye — es cifrado
    estados: dict[str, int]  # {"PENDIENTE": 3, "ENVIADO": 12, "ERROR": 1, ...}
    total: int               # sum(valores)

class ComunicacionesDocenteResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[EstadoComunicacionXDocente]
```

**Notas de implementación**:
- `destinatario` (email del alumno) está cifrado — no se expone ni se descifra.
- El agrupamiento es por `enviado_por` (el docente remitente), no por alumno.
- Si un `enviado_por` no tiene usuario correspondiente en `user` (improbable pero posible por FK sin CASCADE), se omite del resultado.

---

### F9.1(c) — Interacciones por docente y materia

**Endpoint**: `GET /api/v1/auditoria/panel/interacciones`

**Query params**:
```
from_date  : date — opcional
to_date    : date — opcional
actor_id   : UUID — opcional (filtrar por un docente específico)
materia_id : UUID — opcional
```

**Query SQL equivalente**:
```sql
SELECT actor_id, materia_id, accion, COUNT(*) AS cantidad
FROM audit_log
WHERE tenant_id = :tenant_id
  [AND fecha_hora >= :from_date]
  [AND fecha_hora <= :to_date + interval '1 day']
  [AND actor_id = :actor_id_filter]
  [AND materia_id IN (:materias)]   -- scope=own
  [AND materia_id = :materia_id]    -- filtro explícito (scope=all)
GROUP BY actor_id, materia_id, accion
ORDER BY cantidad DESC
```

**Response schema**:
```python
class InteraccionXDocenteMateria(BaseModel):
    model_config = ConfigDict(extra='forbid')
    actor_id: UUID
    nombre: str
    apellidos: str
    materia_id: UUID | None
    accion: str
    cantidad: int

class InteraccionesResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[InteraccionXDocenteMateria]
```

**Notas**:
- `materia_id` puede ser `None` para eventos globales (impersonación, etc.). COORDINADOR no los ve (ver Decisión 2 del design).
- Los nombres de los actores se resuelven en el service (mismo patrón que F9.1.b).

---

### F9.1(d) — Log de últimas acciones

**Endpoint**: `GET /api/v1/auditoria/panel/ultimas-acciones`

**Query params**:
```
limit      : int  — default=200, max=500 (valores fuera de rango → 422)
from_date  : date — opcional
to_date    : date — opcional
actor_id   : UUID — opcional
materia_id : UUID — opcional
```

**Query SQL equivalente**:
```sql
SELECT *
FROM audit_log
WHERE tenant_id = :tenant_id
  [AND fecha_hora >= :from_date]
  [AND fecha_hora <= :to_date + interval '1 day']
  [AND actor_id = :actor_id_filter]
  [AND materia_id IN (:materias)]   -- scope=own
  [AND materia_id = :materia_id]    -- filtro explícito (scope=all)
ORDER BY fecha_hora DESC
LIMIT :limit
```

**Response schema** — dos variantes según scope:

```python
class AuditLogPublicEntry(BaseModel):
    """Para scope=own (COORDINADOR): sin campos de seguridad."""
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    nombre_actor: str
    apellidos_actor: str
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    filas_afectadas: int
    # sin ip, sin user_agent, sin detalle

class AuditLogFullEntry(BaseModel):
    """Para scope=all (ADMIN / FINANZAS): todos los campos."""
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    nombre_actor: str
    apellidos_actor: str
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    detalle: dict | None
    filas_afectadas: int
    ip: str | None
    user_agent: str | None

class UltimasAccionesResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[AuditLogPublicEntry | AuditLogFullEntry]
    limit_aplicado: int
```

El service elige el schema según `scope`: `"all"` → `AuditLogFullEntry`, `"own"` → `AuditLogPublicEntry`.

---

## RBAC — resumen del panel

| Endpoint | Permiso | scope=all | scope=own (COORDINADOR) |
|----------|---------|-----------|------------------------|
| acciones-por-dia | `auditoria:ver` | Todo el tenant | Solo sus materias |
| comunicaciones-docente | `auditoria:ver` | Todo el tenant | Solo comunicaciones con materia_id ∈ sus materias |
| interacciones | `auditoria:ver` | Todo el tenant | Solo audit con materia_id ∈ sus materias |
| ultimas-acciones | `auditoria:ver` | Todos los campos | Subset de campos, solo sus materias |

---

## Tests — Sección 1 (Panel)

### TestAccionesXDia (4 tests)

- `test_acciones_xdia_admin_ve_todo`: ADMIN ve agregación de todo el tenant, sin filtro de materia.
- `test_acciones_xdia_coordinador_scope_own`: COORDINADOR solo ve días con actividad en sus materias.
- `test_acciones_xdia_filtro_fecha`: rango `from_date`/`to_date` acota correctamente.
- `test_acciones_xdia_sin_datos_200_vacio`: response vacía → 200 con `items=[]`.

### TestComunicacionesDocente (5 tests)

- `test_comunicaciones_docente_estados_agrupados`: agrupación correcta por estado (PENDIENTE, ENVIADO, etc.).
- `test_comunicaciones_docente_coordinador_scope_own`: COORDINADOR solo ve comunicaciones de sus materias.
- `test_comunicaciones_docente_filtro_materia`: param `materia_id` acota scope=all.
- `test_comunicaciones_docente_sin_datos_200`: tenant sin comunicaciones → lista vacía.
- `test_comunicaciones_docente_sin_permiso_403`: usuario sin `auditoria:ver` → 403.

### TestInteraccionesXDocenteMateria (5 tests)

- `test_interacciones_todos_modulos`: cuenta acciones de distintos códigos correctamente.
- `test_interacciones_coordinador_scope_own`: no ve auditoría de otras materias.
- `test_interacciones_filtro_actor`: param `actor_id` restringe a un docente.
- `test_interacciones_materia_id_none_invisible_coordinador`: evento sin materia_id no aparece en scope=own.
- `test_interacciones_rbac_otro_tenant_invisible`: aislamiento multi-tenant.

### TestUltimasAcciones (5 tests)

- `test_ultimas_acciones_default_200`: sin params → hasta 200 entradas, las más recientes.
- `test_ultimas_acciones_limit_custom`: `limit=50` → exactamente 50 (si hay ≥50).
- `test_ultimas_acciones_limit_fuera_de_rango_422`: `limit=501` → 422.
- `test_ultimas_acciones_admin_full_fields`: scope=all → campos `ip`, `user_agent`, `detalle` presentes.
- `test_ultimas_acciones_coordinador_public_fields`: scope=own → campos `ip`, `user_agent`, `detalle` ausentes.
