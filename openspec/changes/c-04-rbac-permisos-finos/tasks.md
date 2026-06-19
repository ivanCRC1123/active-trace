## 1. Models — Rol, Permiso, RolPermiso, UserRol

- [x] 1.1 Create `backend/app/models/rol.py` — Rol model (BaseEntityMixin, nombre VARCHAR(50), descripcion VARCHAR(255), UNIQUE tenant_id+nombre)
- [x] 1.2 Create `backend/app/models/permiso.py` — Permiso model (BaseEntityMixin, codigo VARCHAR(100), descripcion VARCHAR(255), modulo VARCHAR(50), UNIQUE tenant_id+codigo)
- [x] 1.3 Create `backend/app/models/rol_permiso.py` — RolPermiso model (BaseEntityMixin, rol_id FK, permiso_id FK, scope VARCHAR(10) DEFAULT 'all', UNIQUE tenant_id+rol_id+permiso_id)
- [x] 1.4 Create `backend/app/models/user_rol.py` — UserRol model (BaseEntityMixin, user_id FK, rol_id FK, UNIQUE tenant_id+user_id+rol_id)
- [x] 1.5 Update `backend/app/models/__init__.py` — export all 4 new models

## 2. Alembic Migration 003

- [x] 2.1 Generate migration revision `003_rol_permiso_user_rol` with all 4 tables
- [x] 2.2 Verify migration upgrades and downgrades cleanly (test by running `alembic upgrade head` then `alembic downgrade -1`)

## 3. Seed Scripts — Permissions Matrix

- [x] 3.1 Create `scripts/seed_permissions.py` with:
  - Idempotent creation of 7 roles: ALUMNO, TUTOR, PROFESOR, COORDINADOR, NEXO, ADMIN, FINANZAS
  - Idempotent creation of all ~20 permissions from §3.3 matrix (each with modulo prefix, snake_case code)
  - Full Rol↔Permiso matrix entries with correct scope ('all' vs 'own') matching ✅/(propio)/— markers
  - UserRol entry assigning ADMIN role to the seed admin user
- [x] 3.2 Verify seed script is idempotent (run twice with no errors or duplicates)

## 4. Repositories

- [ ] 4.1 Create `backend/app/repositories/rol_repository.py` — RolRepository (CRUD, find_by_nombre)
- [ ] 4.2 Create `backend/app/repositories/permiso_repository.py` — PermisoRepository (CRUD, find_by_codigo, find_by_modulo)
- [ ] 4.3 Create `backend/app/repositories/rol_permiso_repository.py` — RolPermisoRepository (CRUD, get_permissions_for_roles, get_roles_for_permission)
- [ ] 4.4 Create `backend/app/repositories/user_rol_repository.py` — UserRolRepository (CRUD, get_roles_for_user, get_users_for_role)
- [ ] 4.5 Update `backend/app/repositories/__init__.py` — export all 4 new repositories

## 5. Permission Resolution Module

- [ ] 5.1 Create `backend/app/core/permissions.py` with:
  - Pydantic model `PermissionCheck(granted: bool, scope: str | None)`
  - `async get_user_permissions(user_id, tenant_id, session) -> dict[str, str]` — resolves all effective permissions for a user (union of roles, 'all' wins over 'own')
  - `async check_permission(user_id, tenant_id, permission_codigo, session) -> PermissionCheck` — checks if user has a specific permission
  - Soft-delete filtering on UserRol, RolPermiso, and Permiso

## 6. AuthService Update — Fetch Roles from UserRol

- [ ] 6.1 Add private helper `_get_user_role_names(user_id, tenant_id) -> list[str]` to AuthService (queries UserRol + Rol for active roles)
- [ ] 6.2 Update `_issue_tokens()` — call `_get_user_role_names` and pass result to `create_access_token(roles=...)` instead of hardcoded `roles=[]`
- [ ] 6.3 Update `refresh()` — call `_get_user_role_names` and pass result to `create_access_token(roles=...)` instead of hardcoded `roles=[]`

## 7. require_permission FastAPI Dependency

- [ ] 7.1 Add `require_permission(permission: str, scoped: bool = False)` factory to `backend/app/core/dependencies.py` (or a new `backend/app/core/permissions.py`)
  - Uses `Depends(get_current_user)` internally
  - Calls `check_permission()` from the permissions module
  - Returns `(CurrentUser, scope | None)` tuple if `scoped=True`
  - Raises HTTP 403 with descriptive message if permission is missing
- [ ] 7.2 Update docstring in `dependencies.py` to move `require_permission` from "reserved for C-04" to active

## 8. Auth Router Update — Demonstrate require_permission

- [ ] 8.1 Add `require_permission` to at least one existing auth-protected endpoint in the auth router (e.g., `/me` or `/2fa/enroll`) to demonstrate and test permission enforcement
- [ ] 8.2 Ensure `get_current_user` dependency remains available for endpoints that require authentication but not specific permissions

## 9. Tests

- [ ] 9.1 Create `backend/tests/test_permissions.py` with:
  - Test user without permission receives 403
  - Test user with permission passes the guard
  - Test role union (multiple roles merge permissions correctly)
  - Test `(propio)` scope resolution (scope='own' vs scope='all')
  - Test soft-deleted role assignments are excluded
  - Test admin CRUD on catalog (create/update rol, permiso, rol_permiso)
- [ ] 9.2 Update `backend/tests/test_auth.py` (or create new tests) to verify:
  - JWT after login contains correct role names from UserRol
  - JWT after refresh contains updated role names
  - User with no roles gets `roles=[]` in JWT
- [ ] 9.3 Update test fixtures to create roles and permissions for test users

## 10. Documentation and Cleanup

- [ ] 10.1 Update `CHANGES.md` — fix migration number from "002" to "003" for C-04 scope
- [ ] 10.2 Update `backend/app/core/dependencies.py` — move `require_permission` comment from "RESERVED for C-04" to active
- [ ] 10.3 Verify all imports work and `openspec/specs/` main specs are consistent with delta specs
