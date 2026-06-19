## Why

The system currently authenticates users (C-03) but has no authorization layer — every authenticated user has the same capabilities, and the JWT always carries `roles=[]`. Without fine-grained RBAC, we cannot enforce the permission matrix defined in `knowledge-base/03_actores_y_roles.md §3.3`, which is the foundation for every business feature from C-05 onward. This change implements the role and permission infrastructure so that: (a) each endpoint can declare what permission it requires, (b) users get only the permissions their roles grant, and (c) the catalog is data-driven and administrable — not hardcoded.

## What Changes

- **New models**: `Rol`, `Permiso`, `RolPermiso` (catalog tables, all inheriting `BaseEntityMixin` for tenant isolation), `UserRol` (many-to-many user ↔ role association).
- **Alembic migration 003**: creates tables `rol`, `permiso`, `rol_permiso`, `user_rol`. (Note: CHANGES.md says "002" but C-03 already used 002 — actual migration is 003.)
- **Seed data**: inserts the 7 domain roles (ALUMNO, TUTOR, PROFESOR, COORDINADOR, NEXO, ADMIN, FINANZAS), all ~20 permissions derived from the matrix in §3.3, and the full Rol↔Permiso matrix entries with scope markers (`all` vs `own`).
- **UserRol seed**: the seed admin user created in C-03 gets the ADMIN role assigned.
- **AuthService update**: `_issue_tokens()` and `refresh()` now query `UserRol` to populate the `roles` claim in the JWT (previously hardcoded `roles=[]`).
- **`get_current_user` update**: the `CurrentUser.roles` field is now populated from the JWT (which was populated from UserRol).
- **`require_permission` dependency**: new FastAPI dependency that checks the user's effective permissions against the required `modulo:accion` for each endpoint. If the user lacks the permission → 403.
- **Permission resolution module**: `core/permissions.py` — resolves effective permissions from the user's roles (union of all `RolPermiso` entries), respecting `scope` (`all` vs `own`).
- **Tests**: user without permission → 403, role union, `(propio)` vs global, admin-manageable catalog.

## Capabilities

### New Capabilities
- `role-catalog`: Data-driven model and CRUD for roles, permissions, and the role↔permission matrix. Catalog tables `Rol`, `Permiso`, `RolPermiso`, plus `UserRol` for user↔role assignment. All tenant-scoped.
- `permission-resolution`: Server-side permission resolution per request. Resolves effective permissions from the union of the user's roles, respecting the `scope` (`all` vs `own`) from `RolPermiso`. Exposes a query function `get_user_permissions(user_id, tenant_id) → list[tuple[str, str]]`.
- `require-permission-guard`: FastAPI dependency `require_permission("modulo:accion")` that validates the current user has the required permission. Returns 403 if lacking. Works with `Depends(get_current_user)` and can optionally check `scope`.

### Modified Capabilities
- `auth-login`: The `_issue_tokens()` method currently hardcodes `roles=[]`. Must now fetch actual role names from `UserRol` and pass them to `create_access_token`.
- `auth-refresh-logout`: The `refresh()` method currently hardcodes `roles=[]`. Must now fetch actual role names from `UserRol` and pass them to `create_access_token`.
- `auth-get-current-user`: The `CurrentUser.roles` field is currently always `[]` from the JWT. After C-04, roles are populated from the JWT, which were populated from `UserRol`.

## Impact

- **Backend models**: 5 new files in `backend/app/models/` (`rol.py`, `permiso.py`, `rol_permiso.py`, `user_rol.py`) + updates to `__init__.py`.
- **Backend repositories**: 4 new repositories in `backend/app/repositories/` (`rol_repository.py`, `permiso_repository.py`, `rol_permiso_repository.py`, `user_rol_repository.py`).
- **Backend core**: new `backend/app/core/permissions.py` module; update `backend/app/core/dependencies.py` (add `require_permission`); update `backend/app/core/auth/service.py` (roles in `_issue_tokens` and `refresh`).
- **Alembic**: new migration `versions/003_rol_permiso_user_rol.py`.
- **Seed**: new seed script `scripts/seed_permissions.py` or inline seed in migration.
- **Tests**: new test file `tests/test_permissions.py` + updates to auth tests to verify roles in JWT.
- **Database**: 4 new tables (`rol`, `permiso`, `rol_permiso`, `user_rol`). All tenant-scoped. Soft-delete enabled.
