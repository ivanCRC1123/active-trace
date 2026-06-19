## Context

C-03 implemented authentication (JWT + Argon2id + 2FA TOTP + refresh rotation + rate limiting + `get_current_user`). The JWT currently carries `roles=[]` because there is no role/authorization infrastructure. Every authenticated user has the same capabilities.

This change implements the RBAC layer defined in `knowledge-base/03_actores_y_roles.md`:
- 7 domain roles (ALUMNO, TUTOR, PROFESOR, COORDINADOR, NEXO, ADMIN, FINANZAS)
- ~20 fine-grained permissions (`modulo:accion`) from the matrix in §3.3
- A `RolPermiso` matrix with scope markers (`all` vs `(propio)`)
- Server-side permission resolution per request
- A `require_permission("modulo:accion")` FastAPI dependency

The catalog must be data-driven (tables, not hardcoded) so that tenants can administer roles and permissions. Existing code in `AuthService._issue_tokens()` and `refresh()` hardcodes `roles=[]` — these must be updated to fetch actual roles from `UserRol`.

All models must respect multi-tenant isolation (`tenant_id` scoping), soft delete, and UUID PKs as established in C-02.

## Goals / Non-Goals

**Goals:**
- Create ROL, PERMISO, ROLPERMISO, USER_ROL tables (migration 003)
- Seed 7 roles, all ~20 permissions from the matrix, full Rol↔Permiso matrix entries with scope
- Seed the admin user (from C-03) with ADMIN role
- Update AuthService._issue_tokens() and refresh() to fetch roles from UserRol
- Update get_current_user dependency (roles now populated in JWT)
- Create require_permission("modulo:accion") FastAPI dependency that returns 403 if lacking
- Create permission resolution module (core/permissions.py)
- Full test coverage: 403 for lacking permission, role union, (propio) scope, admin CRUD on catalog

**Non-Goals:**
- Temporal validity of role assignments (vigencia) → C-07 (equipos docentes)
- Impersonation → C-05 (audit log) / future change
- Frontend UI for admin role management → C-21+ (frontend shell)
- Permission caching layer (Redis) — permissions resolved from DB on each request. Acceptable for MVP; optimization deferred.
- RBAC for WebSocket connections — not needed until real-time features arrive
- Fine-grained resource-level authorization beyond scope marker (e.g., "only comision X") — that is per-endpoint business logic in Services, not generic RBAC

## Decisions

### D1 — Roles in JWT, permissions resolved server-side

The JWT access token carries only ROLE NAMES (e.g., `["ADMIN", "PROFESOR"]`). Permissions are resolved server-side on each request by querying the `RolPermiso` matrix for the user's roles.

**Rationale:**
- Keeps the JWT small (role names are short, typically 1–3 per user).
- Permissions can change without requiring token reissue. If an admin modifies the RolPermiso matrix, the change takes effect on the next request — no need for all users to re-login.
- The matrix is resolved with a single query (`SELECT permiso.codigo, rol_permiso.scope FROM rol_permiso JOIN permiso ... JOIN user_rol WHERE user_rol.user_id = :uid`), which is fast and has no N+1 issues.
- This follows the principle in `knowledge-base/08_arquitectura_propuesta.md §3.1`: "Los permisos se resuelven server-side en cada petición, nunca se almacenan en el token."

**Alternative considered:** Embedding permissions in the JWT (like `["calificaciones:importar", "atrasados:ver", ...]`). Rejected because: (a) JWT size would grow significantly (up to ~20 permissions), (b) permission changes would require token reissue, (c) it violates the documented architecture principle.

### D2 — Data model: four new tables

```
rol (
    id UUID PK,
    tenant_id FK → tenant.id,
    nombre VARCHAR(50) NOT NULL,       -- e.g., "ADMIN", "PROFESOR"
    descripcion VARCHAR(255),           -- optional label
    -- inherited: created_at, updated_at, deleted_at
    UNIQUE(tenant_id, nombre)
)

permiso (
    id UUID PK,
    tenant_id FK → tenant.id,
    codigo VARCHAR(100) NOT NULL,       -- e.g., "calificaciones:importar"
    descripcion VARCHAR(255),
    modulo VARCHAR(50) NOT NULL,        -- e.g., "calificaciones", "atrasados"
    -- inherited: created_at, updated_at, deleted_at
    UNIQUE(tenant_id, codigo)
)

rol_permiso (
    id UUID PK,
    tenant_id FK → tenant.id,
    rol_id UUID FK → rol.id,
    permiso_id UUID FK → permiso.id,
    scope VARCHAR(10) NOT NULL DEFAULT 'all',  -- 'all' | 'own'
    -- inherited: created_at, updated_at, deleted_at
    UNIQUE(tenant_id, rol_id, permiso_id)
)

user_rol (
    id UUID PK,
    tenant_id FK → tenant.id,
    user_id UUID FK → user.id,
    rol_id UUID FK → rol.id,
    -- inherited: created_at, updated_at, deleted_at
    UNIQUE(tenant_id, user_id, rol_id)
)
```

**Rationale:**
- All tables inherit `BaseEntityMixin` → tenant isolation + soft delete + UUID PK + timestamps. This is the standard pattern from C-02.
- `Rol`, `Permiso`, `RolPermiso` are **tenant-scoped catalogs**. Each tenant can have its own role set and matrix (extensibility per `03_actores_y_roles.md §2`: "el conjunto de roles debe ser un catálogo administrable por tenant").
- `scope` on `RolPermiso` encodes the `(propio)` semantic. Default is `'all'` (the role has the permission globally). `'own'` means the permission only applies to the user's own resources (e.g., PROFESOR can `calificaciones:importar` only for their comisiones).
- `UserRol` is a pure many-to-many join. No vigencia fields in C-04 (see Non-Goals). The unique constraint prevents duplicate assignments.

**Alternative considered:** Adding roles as a JSON/array column on User. Rejected because: (a) no referential integrity, (b) cannot join for permission queries, (c) not administrable via catalog.

**Alternative considered:** Using a single `permiso` scope column on `UserRol` to encode `(propio)`. Rejected because `(propio)` is a property of the Rol↔Permiso relationship, not of the user↔role assignment. A PROFESOR always has `(propio)` on `calificaciones:importar`, regardless of which user holds the role.

### D3 — Permission resolution flow

Every authenticated request goes through:

```
Request → get_current_user (JWT → user_id, tenant_id, roles)
       → require_permission("modulo:accion", scoped=False)
           → query: SELECT p.codigo, rp.scope
               FROM user_rol ur
               JOIN rol_permiso rp ON ur.rol_id = rp.rol_id
               JOIN permiso p ON rp.permiso_id = p.id
               WHERE ur.user_id = :user_id
               AND ur.tenant_id = :tenant_id
               AND ur.deleted_at IS NULL
               AND rp.deleted_at IS NULL
               AND p.deleted_at IS NULL
           → check if any row has p.codigo == required_permission
           → if not → 403 Forbidden
           → if yes → pass (optionally with scope info for service layer)
```

**`require_permission` signature:**
```python
def require_permission(
    permission: str,
    scoped: bool = False,
) -> Callable[[CurrentUser, AsyncSession], Awaitable[tuple[CurrentUser, str | None]]]:
    """FastAPI dependency.

    Args:
        permission: The required permission code (e.g., "calificaciones:importar").
        scoped: If True, returns the scope ('all'|'own') so the service can enforce
                resource-level restrictions. If False, just checks existence.

    Returns:
        A dependency that injects a tuple: (current_user, scope) or raises 403.
    """
```

**Performance:** The permission query is a single join across 4 tables, all indexed by FK + tenant_id. For an MVP handling <1000 RPS, this is acceptable. Caching (e.g., Redis with TTL = access_token_expiry) can be added later if needed.

**Alternative considered:** Decoding permissions from a custom JWT claim. Rejected per D1 — permissions must be resolved server-side.

**Alternative considered:** Checking permissions in middleware. Rejected because: (a) middleware cannot easily access route-specific metadata, (b) endpoint-level dependency is more explicit, (c) FastAPI dependencies compose naturally with route parameters and path operations.

### D4 — `core/permissions.py` module structure

```python
# backend/app/core/permissions.py

from uuid import UUID
from sqlalchemy import select, join
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permiso import Permiso
from app.models.rol_permiso import RolPermiso
from app.models.user_rol import UserRol

# ── Data type ──────────────────────────────────────────────────

class PermissionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    granted: bool
    scope: str | None = None  # "all" | "own" | None if not granted

# ── Query ──────────────────────────────────────────────────────

async def get_user_permissions(
    user_id: UUID,
    tenant_id: UUID,
    session: AsyncSession,
) -> dict[str, str]:
    """Resolve all effective permissions for a user.

    Returns a dict mapping permission code → scope.
    Union of all roles. If a permission appears with both 'all' and 'own'
    in different roles, 'all' wins (higher privilege).
    """
    ...

async def check_permission(
    user_id: UUID,
    tenant_id: UUID,
    permission_codigo: str,
    session: AsyncSession,
) -> PermissionCheck:
    """Check if a user has a specific permission. Returns granted + scope."""
    ...
```

### D5 — AuthService updates

**`_issue_tokens`**: After authenticating the user, query `UserRol` → join `Rol` → get `nombre` values:
```python
async def _issue_tokens(self, user: User) -> dict:
    # Fetch actual roles from DB
    roles = await self._get_user_role_names(user.id, user.tenant_id)
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        roles=roles,
    )
    # ... rest unchanged
```

**`refresh`**: Same change — fetch roles before calling `create_access_token`.

**`_get_user_role_names`**: Private helper that queries `UserRol` + `Rol` for active roles:
```python
async def _get_user_role_names(self, user_id: UUID, tenant_id: UUID) -> list[str]:
    stmt = (
        select(Rol.nombre)
        .join(UserRol, UserRol.rol_id == Rol.id)
        .where(
            UserRol.user_id == user_id,
            UserRol.tenant_id == tenant_id,
            UserRol.deleted_at.is_(None),
            Rol.deleted_at.is_(None),
        )
    )
    result = await self._session.execute(stmt)
    return [row[0] for row in result.all()]
```

**Rationale:** The helper lives in AuthService because roles are resolved at token-issuance time, which is an auth concern. No need for a separate UserRolRepository for this simple query (direct SQLAlchemy via session is fine — it's a simple select, not business logic).

### D6 — `require_permission` as a FastAPI dependency

New dependency in `core/dependencies.py` or a new `core/permissions.py` module. Following FastAPI's dependency injection pattern:

```python
from fastapi import Depends, HTTPException, status
from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser

async def require_permission(permission: str, scoped: bool = False):
    """Factory that returns a dependency."""
    async def _check(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[CurrentUser, str | None]:
        check = await check_permission(
            current_user.user_id,
            current_user.tenant_id,
            permission,
            db,
        )
        if not check.granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return current_user, check.scope if scoped else None
    
    return _check
```

Usage in routers:
```python
@router.get("/comisiones/{comision_id}/alumnos-atrasados")
async def get_alumnos_atrasados(
    comision_id: UUID,
    _: tuple[CurrentUser, str | None] = Depends(require_permission("atrasados:ver", scoped=True)),
):
    current_user, scope = _
    # ... service logic handles scope
```

**Alternative considered:** Using a decorator on route handlers. Rejected because: (a) decorators lose FastAPI dependency injection context, (b) dependencies compose naturally with path params, (c) decorators make it harder to test.

### D7 — Seed data approach

The seed will be a Python script (`scripts/seed_permissions.py`) that:
1. Creates the 7 roles if they don't exist (idempotent — checks by `tenant_id + nombre`)
2. Creates all permissions from the matrix (idempotent — checks by `tenant_id + codigo`)
3. Creates the Rol↔Permiso entries for the full matrix (idempotent — checks by `tenant_id + rol_id + permiso_id`)
4. Assigns ADMIN role to the seed admin user (from C-03)

The seed script is run separately from migrations (same pattern as C-03's `seed_admin.py`). It accepts a `--tenant-code` parameter (default: `"tupad"`).

The full permission matrix from `03_actores_y_roles.md §3.3` is encoded as a Python dict:
```python
PERMISSION_MATRIX = {
    "alumno": {
        "estado_academico:ver_propio": "all",
        "evaluacion:reservar": "all",
        "comunicacion:confirmar_aviso": "all",
    },
    "tutor": {
        "comunicacion:confirmar_aviso": "all",
        "atrasados:ver": "all",
        "entregas:detectar_sin_corregir": "all",
        "encuentros:gestionar": "all",
        "guardias:registrar": "own",
    },
    # ... etc for each role
}
```

**Rationale:** A standalone seed script is more maintainable than embedding ~160+ INSERT statements in a migration revision. The migration creates the empty tables; the seed populates them. This separation follows C-03's precedent (`seed_admin.py`).

### D8 — Migration 003 structure

Revision ID: `003_rol_permiso_user_rol`
- Creates `rol`, `permiso`, `rol_permiso`, `user_rol` tables
- All with `BaseEntityMixin` columns (id UUID PK, tenant_id FK, created_at, updated_at, deleted_at)
- Foreign keys: `tenant_id → tenant.id (CASCADE)`, `rol_id → rol.id`, `permiso_id → permiso.id`, `user_id → user.id`
- Unique constraints: `(tenant_id, nombre)` on Rol, `(tenant_id, codigo)` on Permiso, `(tenant_id, rol_id, permiso_id)` on RolPermiso, `(tenant_id, user_id, rol_id)` on UserRol
- Indexes: FK columns for join performance

### D9 — `get_current_user` stays the same structurally

The `get_current_user` dependency in `dependencies.py` already parses `roles` from the JWT payload. After C-04, the JWT will contain actual role names instead of `[]`. No code change is needed in `get_current_user` itself — it already does:

```python
roles: list[str] = payload.get("roles", [])
```

The change is upstream (in `AuthService._issue_tokens` and `refresh`). This is clean separation: auth service issues the token with correct claims; the dependency just reads them.

## Risks / Trade-offs

- **[Permission query on every request adds DB latency]** → Mitigation: The query is a single join across indexed FK columns — typically <5ms. Acceptable for MVP (<1000 RPS). Can be cached in Redis with TTL = ACCESS_TOKEN_EXPIRE_MINUTES if profiling shows it's a bottleneck.
- **[Roles snapshot in JWT may become stale]** → Mitigation: The JWT has only role NAMES, not permissions. If a role is revoked from a user, the old JWT still has that role name for up to 15 min. For fine-grained control, the resource-level authorization in Services can check vigencia (C-07). The 15-min window is acceptable for MVP.
- **[Seed script must be kept in sync with the KB matrix]** → Mitigation: The seed script IS the source of truth for the matrix. Any change to the KB matrix must be reflected in the seed script. A test verifies that all roles in the KB have an entry in the seed.
- **[Migration number conflict]** → Risk: CHANGES.md says "002" but C-03 already used 002. Mitigation: Use 003 for this migration. The CHANGES.md will be updated to reflect the actual migration number.
- **[(propio) scope enforcement is per-endpoint, not automatic]** → Mitigation: The `require_permission` dependency with `scoped=True` returns the scope to the router. Each router must pass the scope to the Service, which implements the actual "own data" filtering. This is intentional — the RBAC layer knows *if* a user has scope-restricted access, but only the business logic knows *what* "own data" means for each resource.
- **[No vigencia in C-04 means roles are valid indefinitely]** → Mitigation: This is intentional per Non-Goals. Vigencia will be added in C-07 when the equipos docentes domain is built. Without vigencia, user-role assignments are permanent until manually removed.

## Migration Plan

1. **Create Alembic migration 003**: `alembic revision --autogenerate -m "003_rol_permiso_user_rol"` (or write manually to be deterministic). Creates 4 tables.
2. **Run migration**: `alembic upgrade head`
3. **Run seed script**: `python scripts/seed_permissions.py --tenant-code tupad`
4. **Rollback**: `alembic downgrade -1` drops the 4 tables. Note: this also removes seed data (cascade from tables).
5. **Re-seed after rollback+upgrade**: re-run the seed script.

## Open Questions

- **¿Exact naming of permission codes?** The KB matrix uses Spanish descriptions like "Importar calificaciones". The permission code should be `modulo:accion` in snake_case, e.g., `calificaciones:importar`. The full list should be derived one-to-one from the matrix rows in §3.3.
- **¿Should Permiso table have a `modulo` column for grouping?** Yes — it helps with admin UI filtering and audit log categorization. Added to the model.
- **¿Seed for ALUMNO, TUTOR, etc. — should we create test users for each role?** Not in C-04. Test users will be created in test fixtures. The seed only creates the ADMIN user's role assignment.
- **¿Should require_permission accept multiple permissions (any/all)?** For MVP, a single permission is sufficient. The pattern can be extended later with `require_any_permission(...)` or `require_all_permissions(...)` if needed.
