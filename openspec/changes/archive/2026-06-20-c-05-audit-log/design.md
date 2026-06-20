## Context

C-04 completed the RBAC layer: roles, permissions, the `require_permission` guard, and the full matrix seeded. The JWT carries role names; permissions are resolved server-side per request. What is missing is any record of *what users do*. This change implements the audit log described in `knowledge-base/04_modelo_de_datos.md §E-AUD` and the impersonation feature described in `knowledge-base/03_actores_y_roles.md §4` and `knowledge-base/08_arquitectura_propuesta.md §3.4–3.5`.

Key constraints from the KB:
- Audit log is **append-only**: no modification, no deletion, ever (KB: "Ningún registro del log puede modificarse ni eliminarse").
- Impersonation must be **distinguishable**, **permissioned**, and every action **attributed to the real actor** (KB §4).
- `tenant_id` is on every entity; audit log is no exception.
- The `materia_id` FK cannot be created yet because the `materia` table does not exist until C-06.

## Goals / Non-Goals

**Goals:**
- Create `audit_log` table with DB-level append-only enforcement (PostgreSQL RULEs)
- Create `AuditLogRepository` (insert + list only), `AuditService` (log + list)
- Create action codes catalog module
- Update `create_access_token`, `CurrentUser`, and `get_current_user` for impersonation
- Add `POST /auth/impersonate` and `POST /auth/impersonate/end` endpoints
- Add `GET /auditoria` endpoint with scope-aware RBAC
- Full test coverage: append-only enforcement, impersonation attribution, permission matrix

**Non-Goals:**
- `materia_id` FK constraint → added in C-06 migration when Materia table is created
- UI for the audit log → C-21+ (frontend)
- Audit events for non-impersonation actions (C-07+ will call AuditService.log() in their services)
- Impersonation persisting across refresh token rotation (impersonation is access-token-scoped only — see D4)
- Cursor-based pagination (page/page_size is sufficient for MVP)

## Decisions

### D1 — AuditLog does NOT use BaseEntityMixin

`BaseEntityMixin` includes `deleted_at` (soft delete) and `updated_at` (modified-at trigger). Both are semantically wrong for an append-only log:
- There is no concept of "deleting" an audit entry.
- There is no concept of "updating" an audit entry.

The `AuditLog` model inherits directly from `Base` and adds only the columns it needs:

```python
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    impersonado_id: Mapped[UUID | None] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    materia_id: Mapped[UUID | None] = mapped_column(
        pg.UUID(as_uuid=True), nullable=True  # no FK until C-06 creates materia table
    )
    accion: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    detalle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    filas_afectadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
```

No `updated_at`, no `deleted_at`, no trigger.

**Alternative considered:** Using `TimeStampedMixin + TenantScopedMixin` without `SoftDeleteMixin`. Rejected because `TimeStampedMixin` adds `updated_at` which implies mutability, and the trigger would fire on any update (which should never happen). A custom model is clearer.

### D2 — Append-only enforced at TWO layers

**App layer**: `AuditLogRepository` exposes only `insert()` and `list()`. No `update()`, `delete()`, or `soft_delete()` methods exist. The model itself has no `deleted_at` column so soft-delete is structurally impossible.

**DB layer**: PostgreSQL RULEs that unconditionally reject UPDATE and DELETE:

```sql
CREATE RULE no_update_audit_log AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit_log AS ON DELETE TO audit_log DO INSTEAD NOTHING;
```

`DO INSTEAD NOTHING` silently swallows the statement (no error, no rows affected). This prevents modification even if someone connects directly to the database or bypasses the ORM.

**Alternative considered (DB layer):** Row-level triggers that `RAISE EXCEPTION`. Rejected because errors can be caught and suppressed in some tooling. `DO INSTEAD NOTHING` is simpler and more tamper-proof.

**Alternative considered:** PostgreSQL RLS (Row-Level Security). Rejected for MVP — requires separate DB roles/policies and adds operational complexity. The two-layer approach is sufficient.

### D3 — materia_id is a naked UUID with no FK (until C-06)

The `materia` table does not exist until C-06 (estructura-academica). Adding `REFERENCES materia(id)` now would require C-06 to run first, creating a hard dependency.

Decision: `materia_id` is stored as `UUID NULLABLE` with no FK constraint. C-06 migration (or a patch after C-06) adds the FK via:

```sql
ALTER TABLE audit_log
  ADD CONSTRAINT fk_audit_log_materia
  FOREIGN KEY (materia_id) REFERENCES materia(id) ON DELETE SET NULL;
```

This keeps C-05 and C-06 independently deployable.

### D4 — Impersonation is scoped to the access token only

Impersonation is carried as a JWT claim (`impersonado_id: str | None`) in the **access token only**. The refresh token is a standard refresh token with no `impersonado_id`.

Consequence: When an access token expires during an impersonation session, the user must call `POST /auth/impersonate` again to continue. A refresh produces a clean (non-impersonating) access token.

This simplifies the implementation (no impersonation state in DB; no special refresh handling) and is more secure (impersonation window bounded by `ACCESS_TOKEN_EXPIRE_MINUTES`, typically 15 min).

**`POST /auth/impersonate` response**: returns only a new `access_token` (the existing refresh token remains valid for the real identity).

**Alternative considered:** Storing impersonation state in DB (`ImpersonationSession` table). Rejected for MVP — overkill when the JWT itself is the session. Can be added later if audit requirements demand session-duration tracking.

### D5 — CurrentUser gains impersonado_id; create_access_token gains impersonado_id param

```python
# schemas/auth.py
class CurrentUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    tenant_id: UUID
    roles: list[str]
    impersonado_id: UUID | None = None  # NEW — None when not impersonating
```

```python
# core/security.py
def create_access_token(
    user_id: UUID,
    tenant_id: UUID,
    roles: list[str],
    impersonado_id: UUID | None = None,  # NEW — backward-compatible default
) -> str:
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "roles": roles,
        "exp": expire,
    }
    if impersonado_id is not None:
        payload["impersonado_id"] = str(impersonado_id)
    return pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
```

```python
# core/dependencies.py — get_current_user (addition only)
impersonado_id_str = payload.get("impersonado_id")
impersonado_id = UUID(impersonado_id_str) if impersonado_id_str else None
return CurrentUser(
    user_id=user_id,
    tenant_id=tenant_id,
    roles=roles,
    impersonado_id=impersonado_id,
)
```

All existing callers of `create_access_token` omit `impersonado_id` and get `None` — no changes required.

### D6 — AuditService.log() is called explicitly, not via decorator/middleware

Business code (services and routers) calls `await audit_service.log(...)` explicitly after performing the operation. Preferred over decorator/middleware because:
- Decorators cannot access business context (`filas_afectadas`, `materia_id`) that is only known after the operation runs.
- Middleware cannot selectively audit only significant actions.
- Explicit calls are easier to test.

For C-05, only the impersonation endpoints call `audit_service.log()`. Future changes (C-07+, C-09, etc.) will add their own `log()` calls in their respective services.

### D7 — Action codes: closed catalog with runtime validation (RN-24)

RN-24 mandates: "El catálogo de códigos válidos es un conjunto definido y versionado; no se admiten códigos arbitrarios."

`audit_codes.py` exports both string constants and a `VALID_ACTION_CODES` frozenset. `AuditService.log()` validates the `accion` parameter against this frozenset before inserting — raising `ValueError` for any unknown code.

```python
# app/core/audit_codes.py
IMPERSONACION_INICIAR    = "IMPERSONACION_INICIAR"
IMPERSONACION_FINALIZAR  = "IMPERSONACION_FINALIZAR"

# Stubs — defined here, called by future changes (C-07+):
CALIFICACIONES_IMPORTAR  = "CALIFICACIONES_IMPORTAR"
PADRON_CARGAR            = "PADRON_CARGAR"
COMUNICACION_ENVIAR      = "COMUNICACION_ENVIAR"
ASIGNACION_MODIFICAR     = "ASIGNACION_MODIFICAR"
LIQUIDACION_CERRAR       = "LIQUIDACION_CERRAR"

# Closed catalog — AuditService.log() validates against this set (RN-24)
VALID_ACTION_CODES: frozenset[str] = frozenset({
    IMPERSONACION_INICIAR,
    IMPERSONACION_FINALIZAR,
    CALIFICACIONES_IMPORTAR,
    PADRON_CARGAR,
    COMUNICACION_ENVIAR,
    ASIGNACION_MODIFICAR,
    LIQUIDACION_CERRAR,
})
```

```python
# AuditService.log() — first line of the method body
if accion not in VALID_ACTION_CODES:
    raise ValueError(f"Unknown audit action code: {accion!r}")
```

Adding a new action code in a future change requires updating `audit_codes.py` in that change — making the catalog explicitly versioned.

**Alternative considered:** Python `Enum`. Rejected — adding a new code requires modifying this file (same coupling), but Enum makes the frozenset redundant and complicates string serialization.

**Alternative considered:** DB table of valid codes. Rejected for MVP — adds a join on every audit insert with no benefit until an admin UI for codes is built.

### D10 — impersonacion:usar permission added to seed (RN-41)

The C-04 seed (`scripts/seed_permissions.py`) was created before C-05 and omits `impersonacion:usar`. C-05 adds it by updating the seed file — which is idempotent and safe to re-run:

- New entry in `PERMISOS`: `{"codigo": "impersonacion:usar", "modulo": "impersonacion", "descripcion": "Impersonar a otro usuario del tenant"}`
- New entry in `PERMISSION_MATRIX["ADMIN"]`: `"impersonacion:usar": "all"`

Only ADMIN gets this permission. Re-running the seed on the existing database is safe: the idempotency checks (`SELECT … WHERE codigo = :c`) skip rows that already exist.

### D11 — INICIAR/FINALIZAR audit events: stateless impersonation trade-off (RN-41)

RN-41 requires: "cada inicio y fin de impersonación genera un evento de auditoría con: actor real, usuario impersonado, fecha/hora de inicio y fecha/hora de fin."

With stateless (JWT-only) impersonation (D4), "fin" is defined as the explicit call to `POST /auth/impersonate/end`. This endpoint:
1. Reads `impersonado_id` from the current JWT before issuing the clean token.
2. Logs `IMPERSONACION_FINALIZAR` with `actor_id = real_actor_id`, `impersonado_id = target_id`.

**Known MVP limitation**: If an impersonating access token expires without the user calling `/end`, no `IMPERSONACION_FINALIZAR` event is logged. The `IMPERSONACION_INICIAR` record remains as evidence of session start. This limitation is documented in the spec and accepted for MVP. DB-level session tracking can be added later if audit completeness requires it.

### D8 — IP and User-Agent captured from FastAPI Request

The impersonation endpoints inject `Request` from `fastapi`:

```python
@router.post("/impersonate")
async def start_impersonate(
    body: ImpersonateRequest,
    request: Request,
    _: tuple[CurrentUser, str | None] = Depends(require_permission("impersonacion:usar")),
):
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    ...
```

### D9 — auditoria:ver scope enforcement in AuditService.list()

The `auditoria:ver` permission exists in the seed (C-04). The matrix gives:
- COORDINADOR: `scope='own'` — sees only entries where `actor_id == their user_id`
- ADMIN: `scope='all'` — sees all entries for the tenant
- FINANZAS: `scope='all'` — sees all entries for the tenant

`AuditService.list()` receives `scope` and `current_user_id`:

```python
async def list(self, *, tenant_id, scope, current_user_id, actor_id_filter=None, ...) -> AuditLogListResponse:
    effective_actor_id = current_user_id if scope == "own" else actor_id_filter
    # passes effective_actor_id to repository as the actor filter
```

## Risks / Trade-offs

- **[RULEs silently swallow writes]** → Any direct DB UPDATE/DELETE returns 0 rows affected and no error. Could confuse a DBA. Mitigation: migration comment documents this explicitly.
- **[materia_id no FK until C-06]** → A bug could write an invalid UUID. Mitigation: services validate materia_id in their own logic. FK is added as soon as C-06 lands.
- **[Impersonation expires silently with the access token]** → If the token expires without calling `/end`, no `IMPERSONACION_FINALIZAR` is logged. The `INICIAR` record remains as evidence. Mitigation: acceptable for MVP; DB-level session tracking can be added later if required.

## Migration Plan

1. Write `alembic/versions/004_audit_log.py` manually (not `--autogenerate` — needed to include RULEs via `op.execute()`).
2. `alembic upgrade head` — creates table, indexes, RULEs on both `trace` and `trace_test`.
3. Update `scripts/seed_permissions.py` — add `impersonacion:usar` to PERMISOS and `PERMISSION_MATRIX["ADMIN"]`.
4. Re-run seed: `python scripts/seed_permissions.py` (idempotent — adds only the missing entry).
5. Rollback migration: `alembic downgrade -1` — drops RULEs then drops table.

## Open Questions

- **Should `POST /auth/impersonate` also rotate the refresh token?** For MVP, no. Can be revisited if audit requirements demand session-duration precision.
- **Should `AuditService.list()` return actor display names (nombre + apellido)?** For MVP, returning `actor_id` only is acceptable. The frontend resolves display names separately. Adding a JOIN now couples `AuditRepository` to the `User` model.
