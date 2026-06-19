## ADDED Requirements

### Requirement: System provides a data-driven role catalog

The system SHALL provide database tables `rol`, `permiso`, `rol_permiso`, and `user_rol` that model the RBAC catalog as data — not hardcoded. All tables SHALL inherit from `BaseEntityMixin` (tenant-scoped, UUID PK, soft-delete, timestamps). The catalog SHALL be administrable at runtime by users with the appropriate permissions.

#### Scenario: Rol table stores role definitions
- **WHEN** the migration is applied
- **THEN** there SHALL be a `rol` table with columns: `id` (UUID PK), `tenant_id` (FK → tenant.id), `nombre` (VARCHAR(50), NOT NULL), `descripcion` (VARCHAR(255)), `created_at`, `updated_at`, `deleted_at`
- **AND** there SHALL be a UNIQUE constraint on `(tenant_id, nombre)`

#### Scenario: Permiso table stores permission definitions
- **WHEN** the migration is applied
- **THEN** there SHALL be a `permiso` table with columns: `id` (UUID PK), `tenant_id` (FK → tenant.id), `codigo` (VARCHAR(100), NOT NULL), `descripcion` (VARCHAR(255)), `modulo` (VARCHAR(50), NOT NULL), `created_at`, `updated_at`, `deleted_at`
- **AND** there SHALL be a UNIQUE constraint on `(tenant_id, codigo)`

#### Scenario: RolPermiso table stores the role-permission matrix
- **WHEN** the migration is applied
- **THEN** there SHALL be a `rol_permiso` table with columns: `id` (UUID PK), `tenant_id` (FK → tenant.id), `rol_id` (FK → rol.id), `permiso_id` (FK → permiso.id), `scope` (VARCHAR(10), NOT NULL, DEFAULT 'all'), `created_at`, `updated_at`, `deleted_at`
- **AND** there SHALL be a UNIQUE constraint on `(tenant_id, rol_id, permiso_id)`
- **AND** `scope` SHALL accept values `'all'` (permission applies globally) or `'own'` (permission applies only to own resources)

#### Scenario: UserRol table stores user-role assignments
- **WHEN** the migration is applied
- **THEN** there SHALL be a `user_rol` table with columns: `id` (UUID PK), `tenant_id` (FK → tenant.id), `user_id` (FK → user.id), `rol_id` (FK → rol.id), `created_at`, `updated_at`, `deleted_at`
- **AND** there SHALL be a UNIQUE constraint on `(tenant_id, user_id, rol_id)`

### Requirement: Seed data populates the 7 domain roles

The system SHALL provide a seed script that creates the 7 domain roles for the initial tenant. The seed SHALL be idempotent (check existence by tenant_id + nombre before inserting).

#### Scenario: Seven roles are seeded for a tenant
- **WHEN** the seed script is executed for tenant "tupad"
- **THEN** the `rol` table SHALL contain exactly these 7 entries for that tenant: ALUMNO, TUTOR, PROFESOR, COORDINADOR, NEXO, ADMIN, FINANZAS
- **AND** each role SHALL have a non-null `nombre` and `tenant_id`

#### Scenario: Seed is idempotent
- **WHEN** the seed script is executed twice for the same tenant
- **THEN** no duplicate entries SHALL be created
- **AND** the second execution SHALL not raise an error

### Requirement: Seed data populates all permissions from the permission matrix

The seed script SHALL create all permission entries derived from the matrix in `knowledge-base/03_actores_y_roles.md §3.3`. Each permission SHALL use `modulo:accion` format.

#### Scenario: All permissions from the matrix are seeded
- **WHEN** the seed script is executed
- **THEN** the `permiso` table SHALL contain entries for: estado_academico:ver_propio, evaluacion:reservar, comunicacion:confirmar_aviso, calificaciones:importar, atrasados:ver, entregas:detectar_sin_corregir, comunicacion:enviar, comunicacion:aprobar, encuentros:gestionar, guardias:registrar, tareas_internas:gestionar, avisos:publicar, equipos:asignar, estructura_academica:gestionar, usuarios:gestionar, auditoria:ver, grilla_salarial:operar, liquidaciones:calcular_cerrar, facturas:gestionar, tenant:configurar
- **AND** each permission SHALL have a non-null `modulo` matching its prefix

### Requirement: Seed data populates the full Rol↔Permiso matrix

The seed script SHALL create RolPermiso entries that match the ✅/—/(propio) markers from `knowledge-base/03_actores_y_roles.md §3.3`. Permissions with ✅ marker get `scope='all'`. Permissions with `(propio)` marker get `scope='own'`. Permissions with — marker get no entry.

#### Scenario: RolPermiso matrix matches the KB specification
- **WHEN** the seed script is executed
- **THEN** ALUMNO SHALL have scope='all' for: estado_academico:ver_propio, evaluacion:reservar, comunicacion:confirmar_aviso
- **AND** TUTOR SHALL have scope='all' for: comunicacion:confirmar_aviso, atrasados:ver, entregas:detectar_sin_corregir, encuentros:gestionar — and scope='own' for: guardias:registrar
- **AND** PROFESOR SHALL have scope='own' for: calificaciones:importar, atrasados:ver, entregas:detectar_sin_corregir, comunicacion:enviar, encuentros:gestionar, guardias:registrar, tareas_internas:gestionar — and scope='all' for: comunicacion:confirmar_aviso
- **AND** COORDINADOR SHALL have scope='all' for: comunicacion:confirmar_aviso, atrasados:ver, entregas:detectar_sin_corregir, comunicacion:enviar, comunicacion:aprobar, encuentros:gestionar, guardias:registrar, tareas_internas:gestionar, avisos:publicar, equipos:asignar, calificaciones:importar — and scope='own' for: auditoria:ver
- **AND** ADMIN SHALL have scope='all' for all permissions except those exclusive to FINANZAS
- **AND** FINANZAS SHALL have scope='all' for: comunicacion:confirmar_aviso, auditoria:ver, grilla_salarial:operar, liquidaciones:calcular_cerrar, facturas:gestionar
- **AND** NEXO SHALL have only: comunicacion:confirmar_aviso (scope='all')

### Requirement: Seed assigns ADMIN role to the seed admin user

The seed script SHALL create a `UserRol` entry assigning the ADMIN role to the initial admin user created in C-03.

#### Scenario: Admin user gets ADMIN role
- **WHEN** the seed script is executed after the admin user exists
- **THEN** a `user_rol` entry SHALL exist linking the admin user's ID to the ADMIN rol ID
- **AND** the entry SHALL be within the same tenant
