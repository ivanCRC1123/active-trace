## Why

The system authenticates (C-03) and authorizes (C-04) users but records nothing about what they do. Without an audit log, it is impossible to answer "who changed what, when, from where" — which is the core identity of activia-trace (the platform's name is *trace*). This change implements the append-only `AuditLog` (E-AUD) defined in `knowledge-base/04_modelo_de_datos.md §E-AUD`, the action codes catalog, and the impersonation feature (deferred from C-04 as Non-Goal) that allows support/ADMIN to diagnose issues while keeping every action attributable to the real actor. After C-05, any service can emit a business event with a standardized code, and authorized users can query the full trail through `GET /api/v1/auditoria`.

## What Changes

- **New model**: `AuditLog` (E-AUD) — append-only, tenant-scoped, NO soft delete, NO `updated_at`. Fields: `id`, `tenant_id`, `fecha_hora` (server_default=now()), `actor_id` (FK → user.id), `impersonado_id` (nullable FK → user.id), `materia_id` (nullable UUID — no FK until C-06 creates Materia), `accion` (VARCHAR 100), `detalle` (JSONB), `filas_afectadas` (INTEGER DEFAULT 0), `ip` (VARCHAR 45), `user_agent` (TEXT).
- **DB-level append-only**: PostgreSQL RULEs that unconditionally reject any UPDATE or DELETE on `audit_log`. Belt-and-suspenders with the app layer.
- **Alembic migration 004**: creates `audit_log` table with 4 indexes: `(tenant_id)`, `(actor_id)`, `(accion)`, `(fecha_hora DESC)`.
- **`app/core/audit_codes.py`**: string constants for all recognized action codes plus `VALID_ACTION_CODES: frozenset[str]`. `AuditService.log()` validates `accion` against this frozenset and raises `ValueError` for unknown codes (RN-24 — closed catalog).
- **`scripts/seed_permissions.py` update**: adds `impersonacion:usar` permission to the PERMISOS catalog and to the ADMIN role matrix (was missing from C-04 seed — required by RN-41).
- **`AuditLogRepository`**: insert-only + tenant-scoped list. No `update()`, `delete()`, or `soft_delete()` methods.
- **`AuditService`**: `log()` (insert) and `list()` (query with filters + pagination).
- **`CurrentUser` schema update**: adds optional `impersonado_id: UUID | None = None`.
- **`create_access_token` update**: accepts optional `impersonado_id: UUID | None = None` (default None — backward compatible, all existing calls unchanged).
- **`get_current_user` update**: extracts `impersonado_id` claim from JWT if present.
- **Impersonation endpoints** in `api/v1/routers/auth.py`:
  - `POST /api/v1/auth/impersonate` — requires `impersonacion:usar`, validates target user in same tenant, issues JWT with `impersonado_id`, logs `IMPERSONACION_INICIAR`.
  - `POST /api/v1/auth/impersonate/end` — requires active impersonation (JWT has `impersonado_id`), issues clean JWT, logs `IMPERSONACION_FINALIZAR`.
- **New router** `api/v1/routers/auditoria.py`: `GET /api/v1/auditoria` — requires `auditoria:ver` (scoped=True); supports filters `actor_id`, `accion`, `materia_id`, `from_date`, `to_date`; pagination `page`/`page_size`.
- **Tests**: append-only DB enforcement (RULEs block UPDATE/DELETE), impersonation attribution (actor_id = real actor), INICIAR/FINALIZAR events, `auditoria:ver` permission matrix, list filters and scope='own'.

## Capabilities

### New Capabilities
- `audit-log-model`: Append-only `audit_log` table (E-AUD) with DB-level write protection, tenant isolation, and action codes catalog.
- `audit-service`: `AuditService.log()` for inserting events; `AuditService.list()` for tenant-scoped querying with filters and pagination.
- `audit-log-router`: `GET /api/v1/auditoria` with scope-aware RBAC (ADMIN/FINANZAS see all; COORDINADOR sees own actions).
- `impersonation`: `POST /api/v1/auth/impersonate` and `/end` — permissioned, audited, distinguishable sessions. Actor is always the real user, never the impersonated one.

### Modified Capabilities
- `auth-get-current-user`: `CurrentUser` gains `impersonado_id: UUID | None`; `get_current_user` extracts it from the JWT claim.
- `auth-security`: `create_access_token` updated to carry optional `impersonado_id` claim.

## Impact

- **Models**: 1 new file `backend/app/models/audit_log.py`; update `models/__init__.py`.
- **Repositories**: 1 new file `backend/app/repositories/audit_log_repository.py`; update `repositories/__init__.py`.
- **Services**: 1 new file `backend/app/services/audit_service.py`; update `services/__init__.py`.
- **Core**: new `backend/app/core/audit_codes.py`; update `security.py` (`create_access_token`); update `dependencies.py` (`get_current_user`); update `schemas/auth.py` (`CurrentUser`).
- **Schemas**: new `backend/app/schemas/auditoria.py` (ImpersonateRequest, ImpersonateResponse, AuditLogResponse, AuditLogListResponse).
- **Routers**: new `backend/app/api/v1/routers/auditoria.py`; add 2 endpoints to `auth.py`; register in `main.py`.
- **Alembic**: new migration `versions/004_audit_log.py`.
- **Tests**: new `backend/tests/test_audit_log.py`.
- **Database**: 1 new table `audit_log`, 4 indexes, 2 PostgreSQL RULEs.
