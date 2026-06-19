## ADDED Requirements

### Requirement: System resolves effective permissions from user roles

The system SHALL provide a function `get_user_permissions(user_id, tenant_id, session)` that resolves all effective permissions for a user by computing the union of permissions from all their roles. The function SHALL return a mapping of permission code → scope. If the same permission appears with both `'all'` and `'own'` scopes from different roles, `'all'` SHALL win.

#### Scenario: Single role returns its permissions
- **WHEN** a user has the ADMIN role (which has scope='all' for auditoria:ver)
- **AND** `get_user_permissions` is called for that user
- **THEN** the result SHALL include `{"auditoria:ver": "all"}`

#### Scenario: Multiple roles union returns merged permissions
- **WHEN** a user has both PROFESOR (scope='own' for calificaciones:importar) and COORDINADOR (scope='all' for calificaciones:importar)
- **AND** `get_user_permissions` is called for that user
- **THEN** the result SHALL include `{"calificaciones:importar": "all"}` (higher privilege wins)

#### Scenario: Role with no matching permissions returns empty dict
- **WHEN** a user has only the NEXO role
- **AND** `get_user_permissions` is called for that user
- **THEN** the result SHALL include only those permissions assigned to NEXO
- **AND** SHALL NOT include permissions from other roles

#### Scenario: Soft-deleted role assignments are excluded
- **WHEN** a user had a PROFESOR role that was soft-deleted (deleted_at IS NOT NULL)
- **AND** `get_user_permissions` is called for that user
- **THEN** permissions from the soft-deleted role SHALL NOT be included in the result

### Requirement: System checks if a user has a specific permission

The system SHALL provide a function `check_permission(user_id, tenant_id, permission_codigo, session)` that returns whether a user has a specific permission and with what scope. The function SHALL return `PermissionCheck(granted=True, scope="all")` if the user has the permission, or `PermissionCheck(granted=False, scope=None)` if not.

#### Scenario: User has the requested permission
- **WHEN** a user with ADMIN role calls `check_permission` for "estructura_academica:gestionar"
- **THEN** the result SHALL have `granted=True` and `scope="all"`

#### Scenario: User does not have the requested permission
- **WHEN** a user with ALUMNO role calls `check_permission` for "calificaciones:importar"
- **THEN** the result SHALL have `granted=False` and `scope=None`

#### Scenario: User has permission with scope='own'
- **WHEN** a user with PROFESOR role calls `check_permission` for "calificaciones:importar"
- **THEN** the result SHALL have `granted=True` and `scope="own"`
