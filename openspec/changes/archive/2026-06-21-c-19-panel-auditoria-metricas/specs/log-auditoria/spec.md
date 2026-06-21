# Spec — Log Completo de Auditoría (F9.2)

> Read-only sobre `audit_log`. Sin migración. Paginado.

---

## Inconsistencia documentada

F9.2 en `06_funcionalidades.md` declara `Quién: ADMIN`. La matriz §3.3 asigna `auditoria:ver` a ADMIN, FINANZAS y COORDINADOR (propio). **Se sigue la matriz.** Acción pendiente: corregir `06_funcionalidades.md`.

---

## Endpoint

`GET /api/v1/auditoria/log`

**Query params**:
```
from_date  : date   (YYYY-MM-DD) — opcional
to_date    : date   (YYYY-MM-DD) — opcional
actor_id   : UUID               — opcional
accion     : str                — código exacto, p.ej. "COMUNICACION_ENVIAR" — opcional
materia_id : UUID               — opcional (ignorado si scope=own)
page       : int    — default=1, min=1
page_size  : int    — default=50, max=200
```

**Acceso**:
- `require_permission("auditoria:ver", scoped=True)` en todos los casos.
- `scope="all"` (ADMIN / FINANZAS) → sin restricción de materia.
- `scope="own"` (COORDINADOR) → solo registros con `materia_id IN (materias propias)`.

---

## Query SQL equivalente

```sql
SELECT
    al.id,
    al.fecha_hora,
    al.actor_id,
    u.nombre         AS nombre_actor,
    u.apellidos      AS apellidos_actor,
    al.impersonado_id,
    al.materia_id,
    al.accion,
    al.detalle,           -- solo en scope=all
    al.filas_afectadas,
    al.ip,                -- solo en scope=all
    al.user_agent         -- solo en scope=all
FROM audit_log al
LEFT JOIN "user" u ON u.id = al.actor_id AND u.tenant_id = :tenant_id
WHERE al.tenant_id = :tenant_id
  [AND al.fecha_hora >= :from_date]
  [AND al.fecha_hora <= :to_date + interval '1 day']
  [AND al.actor_id   = :actor_id_filter]
  [AND al.accion     = :accion_filter]
  [AND al.materia_id IN (:materias)]   -- scope=own
  [AND al.materia_id = :materia_id]    -- filtro explícito scope=all
ORDER BY al.fecha_hora DESC
LIMIT :page_size OFFSET (:page - 1) * :page_size
```

---

## Response Schema

```python
class AuditLogPublicEntry(BaseModel):
    """scope=own (COORDINADOR): sin campos de seguridad."""
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    nombre_actor: str | None   # None si el user fue borrado (soft-delete)
    apellidos_actor: str | None
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    filas_afectadas: int

class AuditLogFullEntry(BaseModel):
    """scope=all (ADMIN / FINANZAS): todos los campos."""
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    nombre_actor: str | None
    apellidos_actor: str | None
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    detalle: dict | None
    filas_afectadas: int
    ip: str | None
    user_agent: str | None

class PaginatedAuditLogResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[AuditLogPublicEntry | AuditLogFullEntry]
    total: int
    page: int
    page_size: int
    pages: int   # ceil(total / page_size)
```

---

## Comportamiento esperado

- **200** con `items=[]` si el rango no tiene datos (nunca 404 por filtro).
- **422** si `page < 1` o `page_size > 200`.
- **403** si el usuario no tiene `auditoria:ver`.
- Los campos `detalle`, `ip`, `user_agent` están presentes solo en `AuditLogFullEntry` (scope=all). El service elige el schema según el scope del usuario; nunca se mezclan en la misma response.
- `nombre_actor` / `apellidos_actor` pueden ser `None` si el usuario fue soft-deleted (el log es inmutable; el usuario puede haberse desactivado después).
- La impersonación se representa: `actor_id` = quien impersonó, `impersonado_id` = quien fue impersonado. Ambos visibles siempre que el scope lo permita.

---

## PII — campos NO expuestos

- `user.email` — cifrado, nunca en respuesta.
- `user.dni`, `user.cuil`, `user.cbu` — cifrados, nunca en respuesta.
- `Comunicacion.destinatario` — no aplica a este endpoint (es sobre `audit_log`).

---

## Tests — Sección 2 (Log Completo)

### TestLogAuditoria (8 tests)

- `test_log_admin_todos_los_campos`: scope=all → response incluye `detalle`, `ip`, `user_agent`.
- `test_log_coordinador_sin_campos_seguros`: scope=own → `detalle`, `ip`, `user_agent` ausentes en response.
- `test_log_coordinador_solo_sus_materias`: COORDINADOR no ve registros de otras materias ni sin materia.
- `test_log_filtro_actor_id`: `actor_id` param acota a un solo usuario.
- `test_log_filtro_accion`: `accion=COMUNICACION_ENVIAR` acota por código.
- `test_log_filtro_fecha_rango`: `from_date` y `to_date` acota correctamente.
- `test_log_paginacion`: page=1 y page=2 devuelven conjuntos distintos; `total` es consistente.
- `test_log_otro_tenant_invisible`: aislamiento multi-tenant estricto.

### TestLogRBAC (2 tests)

- `test_log_sin_permiso_403`: usuario sin `auditoria:ver` → 403 en todos los endpoints.
- `test_log_finanzas_scope_all`: FINANZAS tiene scope=all, ve todo el tenant.
