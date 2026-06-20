## 1. AuditLog Model

- [x] 1.1 Create `backend/app/models/audit_log.py` — custom Base (NOT BaseEntityMixin): `id` (UUID PK, server_default gen_random_uuid()), `tenant_id` (naked UUID, no FK — FK cascade conflicts with append-only RULEs, index), `fecha_hora` (TIMESTAMPTZ, server_default now(), index), `actor_id` (naked UUID, no FK — same reason, index), `impersonado_id` (nullable naked UUID, no FK), `materia_id` (nullable UUID, no FK — awaits C-06), `accion` (VARCHAR 100, index), `detalle` (JSONB nullable), `filas_afectadas` (INTEGER default 0), `ip` (VARCHAR 45 nullable), `user_agent` (TEXT nullable). No `updated_at`, no `deleted_at`.
- [x] 1.2 Update `backend/app/models/__init__.py` — export AuditLog

## 2. Alembic Migration 004

- [x] 2.1 Create `backend/alembic/versions/c05af7b8d9e1_004_audit_log.py` (written manually, NOT `--autogenerate`) with:
  - `upgrade()`: CREATE TABLE audit_log (no FK constraints), CREATE INDEX ×4 (`idx_audit_log_tenant`, `idx_audit_log_actor`, `idx_audit_log_accion`, `idx_audit_log_fecha`), `CREATE RULE no_update_audit_log AS ON UPDATE TO audit_log DO INSTEAD NOTHING`, `CREATE RULE no_delete_audit_log AS ON DELETE TO audit_log DO INSTEAD NOTHING`
  - `downgrade()`: `DROP RULE IF EXISTS no_update_audit_log ON audit_log`, `DROP RULE IF EXISTS no_delete_audit_log ON audit_log`, DROP TABLE audit_log
- [x] 2.2 Verify `alembic upgrade head` succeeds on `trace` and `trace_test`
- [x] 2.3 Verify `alembic downgrade -1` then `alembic upgrade head` roundtrips cleanly

## 3. Action Codes Module

- [x] 3.1 Create `backend/app/core/audit_codes.py` with:
  - String constants: `IMPERSONACION_INICIAR`, `IMPERSONACION_FINALIZAR` (active in C-05)
  - Stubs for future changes: `CALIFICACIONES_IMPORTAR`, `PADRON_CARGAR`, `COMUNICACION_ENVIAR`, `ASIGNACION_MODIFICAR`, `LIQUIDACION_CERRAR`
  - `VALID_ACTION_CODES: frozenset[str]` containing ALL of the above (RN-24 — closed catalog)

## 3b. Seed update — impersonacion:usar (RN-41)

- [x] 3b.1 Update `backend/scripts/seed_permissions.py`:
  - Add to `PERMISOS`: `{"codigo": "impersonacion:usar", "modulo": "impersonacion", "descripcion": "Impersonar a otro usuario del tenant"}`
  - Add to `PERMISSION_MATRIX["ADMIN"]`: `"impersonacion:usar": "all"`
- [x] 3b.2 Re-run seed against `trace` DB: `python scripts/seed_permissions.py` (idempotent — adds only the missing entries)
- [x] 3b.3 Verify `impersonacion:usar` appears in `permiso` table and linked in `rol_permiso` for the ADMIN role

## 4. AuditLogRepository

- [x] 4.1 Create `backend/app/repositories/audit_log_repository.py` — AuditLogRepository:
  - `__init__(self, session: AsyncSession, tenant_id: UUID)`
  - `async def insert(self, *, actor_id: UUID, accion: str, detalle: dict | None = None, filas_afectadas: int = 0, ip: str | None = None, user_agent: str | None = None, impersonado_id: UUID | None = None, materia_id: UUID | None = None) -> AuditLog`
  - `async def list(self, *, actor_id_filter: UUID | None = None, accion_filter: str | None = None, materia_id_filter: UUID | None = None, from_date: datetime | None = None, to_date: datetime | None = None, page: int = 1, page_size: int = 50) -> tuple[list[AuditLog], int]`
  - NO `update()`, `delete()`, or `soft_delete()` methods
- [x] 4.2 Update `backend/app/repositories/__init__.py` — export AuditLogRepository

## 5. AuditService

- [x] 5.1 Create `backend/app/services/audit_service.py` — AuditService:
  - `__init__(self, session: AsyncSession)`
  - `async def log(self, *, current_user: CurrentUser, accion: str, detalle: dict | None = None, filas_afectadas: int = 0, ip: str | None = None, user_agent: str | None = None, materia_id: UUID | None = None) -> None`:
    - First line: `if accion not in VALID_ACTION_CODES: raise ValueError(f"Unknown audit action code: {accion!r}")` (RN-24)
    - Extracts actor_id, tenant_id, impersonado_id from current_user
    - Creates AuditLogRepository(session, tenant_id) and calls insert()
  - `async def list(self, *, tenant_id: UUID, scope: str, current_user_id: UUID, actor_id_filter: UUID | None = None, accion_filter: str | None = None, materia_id_filter: UUID | None = None, from_date: datetime | None = None, to_date: datetime | None = None, page: int = 1, page_size: int = 50) -> AuditLogListResponse` — resolves effective_actor_id from scope; delegates to repository
- [x] 5.2 Update `backend/app/services/__init__.py` — export AuditService

## 6. Schemas

- [x] 6.1 Create `backend/app/schemas/auditoria.py`:
  - `ImpersonateRequest(BaseModel, extra='forbid')`: `target_user_id: UUID`
  - `ImpersonateResponse(BaseModel, extra='forbid')`: `access_token: str`, `impersonado_id: UUID`
  - `AuditLogResponse(BaseModel, extra='forbid')`: `id: UUID`, `fecha_hora: datetime`, `actor_id: UUID`, `impersonado_id: UUID | None`, `materia_id: UUID | None`, `accion: str`, `detalle: dict | None`, `filas_afectadas: int`, `ip: str | None`, `user_agent: str | None`
  - `AuditLogListResponse(BaseModel, extra='forbid')`: `items: list[AuditLogResponse]`, `total: int`, `page: int`, `page_size: int`
- [x] 6.2 Update `backend/app/schemas/auth.py` — add `impersonado_id: UUID | None = None` to `CurrentUser`

## 7. create_access_token Update

- [x] 7.1 Update `backend/app/core/security.py`:
  - Add `impersonado_id: UUID | None = None` parameter to `create_access_token` (backward-compatible — all existing callers omit it)
  - If `impersonado_id is not None`: include `"impersonado_id": str(impersonado_id)` in the JWT payload

## 8. get_current_user Update

- [x] 8.1 Update `backend/app/core/dependencies.py` — `get_current_user`:
  - `impersonado_id_str = payload.get("impersonado_id")`
  - `impersonado_id = UUID(impersonado_id_str) if impersonado_id_str else None`
  - Populate `CurrentUser(... impersonado_id=impersonado_id)`

## 9. Impersonation Endpoints (in auth router)

- [x] 9.1 Add `POST /api/auth/impersonate` to `backend/app/api/v1/routers/auth.py`:
  - Parameters: `body: ImpersonateRequest`, `request: Request`, `_: Depends(require_permission("impersonacion:usar"))`
  - Extract `current_user` from the dependency tuple
  - Validate target user exists in same tenant and `is_active=True` (via UserRepository); 404 if not found, 400 if inactive
  - Issue new access token: `create_access_token(user_id=current_user.user_id, tenant_id=..., roles=current_user.roles, impersonado_id=target_id)`
  - Build `ctx_for_log` with `impersonado_id=body.target_user_id` (INICIAR fix — current_user.impersonado_id is None pre-impersonation)
  - Call `AuditService.log(current_user=ctx_for_log, accion=IMPERSONACION_INICIAR, ...)`
  - Return `ImpersonateResponse`
- [x] 9.2 Add `POST /api/auth/impersonate/end` to auth router:
  - Parameters: `request: Request`, `current_user: CurrentUser = Depends(get_current_user)`
  - If `current_user.impersonado_id is None` → raise HTTP 400 `{"detail": "No active impersonation session"}`
  - Capture `impersonado_id = current_user.impersonado_id` before issuing new token
  - Issue clean token: `create_access_token(user_id=..., tenant_id=..., roles=..., impersonado_id=None)`
  - Call `AuditService.log(current_user=current_user, accion=IMPERSONACION_FINALIZAR, detalle={"target_user_id": str(impersonado_id)}, filas_afectadas=1, ip=..., user_agent=...)`
  - Return `{"access_token": new_token, "token_type": "bearer"}`

## 10. Auditoria Router

- [x] 10.1 Create `backend/app/api/v1/routers/auditoria.py`:
  - `GET /api/v1/auditoria`
  - Query params: `actor_id: UUID | None = None`, `accion: str | None = None`, `materia_id: UUID | None = None`, `from_date: datetime | None = None`, `to_date: datetime | None = None`, `page: int = 1`, `page_size: int = Query(default=50, le=200)`
  - Dependency: `Depends(require_permission("auditoria:ver", scoped=True))`
  - Extract `(current_user, scope)` from the dependency tuple
  - Call `AuditService.list(tenant_id=current_user.tenant_id, scope=scope, current_user_id=current_user.user_id, ...)`
  - Return `AuditLogListResponse`
- [x] 10.2 Register `auditoria_router` in `backend/app/main.py` under prefix `/api/v1`

## 11. Tests

- [x] 11.1 Create `backend/tests/test_audit_log.py` — 24 tests across 6 classes; all passing (220/221 suite, 1 pre-existing failure from C-03)

  **Catalog validation (RN-24):** ✓
  **Append-only (DB layer):** ✓
  **Impersonation JWT:** ✓
  **Impersonation audit:** ✓
  **RBAC/validation:** ✓
  **auditoria:ver:** ✓
