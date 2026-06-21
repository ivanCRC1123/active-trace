# C-19 — `panel-auditoria-metricas` — Tasks

> Governance: ALTO. Expone datos de auditoría real; RBAC correcto es crítico.
> Sin migración Alembic. Read-only sobre `audit_log` (C-05) y `comunicacion` (C-12).

**Leer antes de implementar**:
- `openspec/changes/c-19-panel-auditoria-metricas/design.md` — las 6 decisiones (especialmente Decisión 2 RBAC y Decisión 4 PII).
- `openspec/changes/c-19-panel-auditoria-metricas/specs/panel-interacciones/spec.md`
- `openspec/changes/c-19-panel-auditoria-metricas/specs/log-auditoria/spec.md`
- `knowledge-base/03_actores_y_roles.md` §3.3 — matriz RBAC.
- `backend/app/repositories/audit_log_repository.py` — existente C-05.
- `backend/app/repositories/comunicacion_repository.py` — existente C-12.
- `backend/app/core/permissions.py` — `require_permission(..., scoped=True)`.

---

## SECCIÓN 1 — Repositorios

### 1. `AuditoriaRepository` (nuevo)

- [x] 1.1 Crear `backend/app/repositories/auditoria_repository.py`:
  - `AuditoriaRepository.__init__(session, tenant_id)`
  - `acciones_por_dia(*, from_date, to_date, materia_ids)` → `list[AccionPorDiaRow]`
    - `AccionPorDiaRow`: namedtuple o dataclass simple (`fecha: date`, `cantidad: int`)
    - SQL: `SELECT DATE(fecha_hora), COUNT(*) GROUP BY 1 ORDER BY 1`
    - `materia_ids=None` → sin filtro; `materia_ids=set()` → return `[]` inmediato (coordinador sin asignaciones)
  - `interacciones_por_docente_materia(*, from_date, to_date, actor_id_filter, materia_ids)` → `list[InteraccionRow]`
    - `InteraccionRow`: (`actor_id: UUID`, `materia_id: UUID | None`, `accion: str`, `cantidad: int`)
    - SQL: `SELECT actor_id, materia_id, accion, COUNT(*) GROUP BY 1,2,3 ORDER BY cantidad DESC`
  - `ultimas_acciones(*, limit, from_date, to_date, actor_id_filter, materia_ids)` → `list[AuditLog]`
    - `limit` clampado a [1, 500] en el service antes de pasar al repo
    - SQL: `SELECT ... ORDER BY fecha_hora DESC LIMIT :limit`
  - `log_completo(*, from_date, to_date, actor_id_filter, accion_filter, materia_ids, page, page_size)` → `tuple[list[AuditLog], int]`
    - Paginado; `total` es COUNT del subquery
  - Todos los métodos: primer filtro siempre `WHERE audit_log.tenant_id = :tenant_id`
  - `materia_ids=None` → sin cláusula de materia (scope=all)
  - `materia_ids=set()` → return vacío inmediato (COORDINADOR sin materias propias)

- [x] 1.2 Actualizar `backend/app/repositories/__init__.py` — exportar `AuditoriaRepository`.

### 2. `ComunicacionRepository` — método adicional

- [x] 2.1 Agregar `estado_por_docente(*, materia_ids)` → `list[EstadoDocenteRow]` al `ComunicacionRepository` existente:
  - `EstadoDocenteRow`: (`enviado_por: UUID`, `estado: str`, `cantidad: int`)
  - SQL: `SELECT enviado_por, estado, COUNT(*) GROUP BY 1,2`
  - `WHERE tenant_id=... AND deleted_at IS NULL [AND materia_id IN (:materias)]`
  - Misma semántica de `materia_ids`: `None` = sin filtro, `set()` = return vacío.

---

## SECCIÓN 2 — Service

- [x] 3.1 Crear `backend/app/services/auditoria_service.py`:
  - `AuditoriaService.__init__(session, auditoria_repo, comunicacion_repo, asignacion_repo)`
  - `_get_materia_ids_scoped(*, actor_id, scope)` → `set[UUID] | None`:
    - `scope="all"` → return `None` (sin restricción)
    - `scope="own"` → `SELECT DISTINCT materia_id FROM asignacion WHERE usuario_id=... AND deleted_at IS NULL AND materia_id IS NOT NULL`
    - Si el set resultante está vacío → return `set()` (COORDINADOR sin materias → todo vacío)
  - `get_acciones_por_dia(*, actor_id, scope, filtros)` → `AccionesXDiaResponse`
  - `get_comunicaciones_docente(*, actor_id, scope, filtros)` → `ComunicacionesDocenteResponse`
    - Resuelve nombres: `SELECT id, nombre, apellidos FROM "user" WHERE id IN (:ids) AND tenant_id=... AND deleted_at IS NULL`
    - Agrupa rows por `enviado_por`, construye `dict[str, int]` de estados
    - Usuarios no encontrados (soft-deleted) se omiten del resultado
  - `get_interacciones(*, actor_id, scope, filtros)` → `InteraccionesResponse`
    - Resuelve nombres de actores (mismo patrón)
  - `get_ultimas_acciones(*, actor_id, scope, filtros)` → `UltimasAccionesResponse`
    - Clampea `limit` a [1, 500]; devuelve 422 si `limit > 500` (validación en schema, no en service)
    - Elige schema según scope: `AuditLogFullEntry` (all) vs `AuditLogPublicEntry` (own)
    - Resuelve nombres de actores
  - `get_log_completo(*, actor_id, scope, filtros)` → `tuple[list[LogEntry], int]`
    - Misma lógica de schema dual según scope
    - `page_size` max=200; validación en schema de request

- [x] 3.2 Actualizar `backend/app/services/__init__.py` — exportar `AuditoriaService`.

---

## SECCIÓN 3 — Schemas

- [x] 4.1 Crear `backend/app/schemas/auditoria.py`:

  **Schemas de request (query params como Pydantic BaseModel para validación)**:
  ```python
  class PanelFiltros(BaseModel):
      model_config = ConfigDict(extra='forbid')
      from_date: date | None = None
      to_date: date | None = None
      materia_id: UUID | None = None
      actor_id: UUID | None = None
      limit: int = Field(default=200, ge=1, le=500)  # para ultimas-acciones

  class LogFiltros(BaseModel):
      model_config = ConfigDict(extra='forbid')
      from_date: date | None = None
      to_date: date | None = None
      actor_id: UUID | None = None
      accion: str | None = None
      materia_id: UUID | None = None
      page: int = Field(default=1, ge=1)
      page_size: int = Field(default=50, ge=1, le=200)
  ```

  **Schemas de response**:
  - `AccionXDia`: `fecha: date`, `cantidad: int`
  - `AccionesXDiaResponse`: `items: list[AccionXDia]`, `total_acciones: int`
  - `EstadoComunicacionXDocente`: `actor_id`, `nombre`, `apellidos`, `estados: dict[str, int]`, `total: int`
  - `ComunicacionesDocenteResponse`: `items: list[EstadoComunicacionXDocente]`
  - `InteraccionXDocenteMateria`: `actor_id`, `nombre`, `apellidos`, `materia_id`, `accion`, `cantidad`
  - `InteraccionesResponse`: `items: list[InteraccionXDocenteMateria]`
  - `AuditLogPublicEntry`: sin `detalle`, `ip`, `user_agent`
  - `AuditLogFullEntry`: con `detalle`, `ip`, `user_agent`
  - `UltimasAccionesResponse`: `items: list[...]`, `limit_aplicado: int`
  - `PaginatedAuditLogResponse`: `items`, `total`, `page`, `page_size`, `pages`

  Todos con `model_config = ConfigDict(extra='forbid')`.

---

## SECCIÓN 4 — Router

- [x] 5.1 Crear `backend/app/api/v1/routers/auditoria.py`:
  - Prefix: `/api/v1/auditoria`
  - Guard en todos los endpoints: `Depends(require_permission("auditoria:ver", scoped=True))`
  - `GET /panel/acciones-por-dia` → `AccionesXDiaResponse`
  - `GET /panel/comunicaciones-docente` → `ComunicacionesDocenteResponse`
  - `GET /panel/interacciones` → `InteraccionesResponse`
  - `GET /panel/ultimas-acciones` → `UltimasAccionesResponse`
  - `GET /log` → `PaginatedAuditLogResponse`
  - Cada handler: extrae `(current_user, scope)`, construye filtros, llama service.
  - NO llama `AuditLogRepository.insert()` en ningún endpoint (lecturas no se auditan).
  - Mapeo: `ValueError` → 422 (validación de `limit`, `page_size`).

- [x] 5.2 Registrar en `backend/app/main.py`:
  ```python
  from app.api.v1.routers import auditoria
  app.include_router(auditoria.router)
  ```

---

## SECCIÓN 5 — Tests

- [x] 6.1 Crear `backend/tests/test_auditoria.py` con fixture `aud_db` (yield, cleanup scoped a tenants propios):

  **TestAccionesXDia** (4 tests):
  - `test_acciones_xdia_admin_ve_todo`
  - `test_acciones_xdia_coordinador_scope_own`
  - `test_acciones_xdia_filtro_fecha`
  - `test_acciones_xdia_sin_datos_200_vacio`

  **TestComunicacionesDocente** (5 tests):
  - `test_comunicaciones_docente_estados_agrupados`
  - `test_comunicaciones_docente_coordinador_scope_own`
  - `test_comunicaciones_docente_filtro_materia`
  - `test_comunicaciones_docente_sin_datos_200`
  - `test_comunicaciones_docente_sin_permiso_403`

  **TestInteraccionesXDocenteMateria** (5 tests):
  - `test_interacciones_todos_modulos`
  - `test_interacciones_coordinador_scope_own`
  - `test_interacciones_filtro_actor`
  - `test_interacciones_materia_id_none_invisible_coordinador`
  - `test_interacciones_rbac_otro_tenant_invisible`

  **TestUltimasAcciones** (5 tests):
  - `test_ultimas_acciones_default_200`
  - `test_ultimas_acciones_limit_custom`
  - `test_ultimas_acciones_limit_fuera_de_rango_422`
  - `test_ultimas_acciones_admin_full_fields`
  - `test_ultimas_acciones_coordinador_public_fields`

  **TestLogAuditoria** (8 tests):
  - `test_log_admin_todos_los_campos`
  - `test_log_coordinador_sin_campos_seguros`
  - `test_log_coordinador_solo_sus_materias`
  - `test_log_filtro_actor_id`
  - `test_log_filtro_accion`
  - `test_log_filtro_fecha_rango`
  - `test_log_paginacion`
  - `test_log_otro_tenant_invisible`

  **TestLogRBAC** (2 tests):
  - `test_log_sin_permiso_403`
  - `test_log_finanzas_scope_all`

  **Total: ~29 tests**

---

## Criterios de Aceptación

- [x] Sin migración Alembic generada ni ejecutada.
- [x] Ningún endpoint llama `AuditLogRepository.insert()` (lecturas no se auditan).
- [x] COORDINADOR con scope=own nunca recibe datos de otras materias (assert en tests).
- [x] COORDINADOR nunca recibe `detalle`, `ip`, `user_agent` en ninguna response.
- [x] `email`, `dni`, `cuil`, `cbu` del usuario nunca aparecen en ninguna response.
- [x] `Comunicacion.destinatario` nunca se descifra ni se expone.
- [x] `auditoria:ver` es el único permiso usado; no se crean permisos nuevos.
- [x] `extra='forbid'` en todos los schemas.
- [x] Suite completa: 0 regresiones en C-01 a C-18. 647 passed, 0 failed.
- [x] 29 tests del módulo en verde.
- [ ] Inconsistencia F9.2 en `06_funcionalidades.md` corregida (quién puede acceder). ← diferido a C-24 frontend

---

## Decisiones pendientes (confirmar antes de implementar)

Ver `design.md` §Decisiones abiertas:
- **OD-1**: ¿COORDINADOR debe ver eventos sin `materia_id`? (propuesta: NO)
- **OD-2**: ¿`limit` de últimas-acciones tiene cap por tenant o solo por request? (propuesta: cap=500 hardcodeado)
- **OD-3**: ¿`ip` y `user_agent` para COORDINADOR? (propuesta: NO)
- **OD-4**: ¿Filtrar por tipo de acción en interacciones? (propuesta: todos los tipos, sin filtro)
