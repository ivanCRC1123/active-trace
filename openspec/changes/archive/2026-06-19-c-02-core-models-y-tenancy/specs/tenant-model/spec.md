## ADDED Requirements

### Requirement: Tenant entity as root of multi-tenancy

The system SHALL have a `Tenant` entity as the root of all multi-tenant data. Each tenant represents an institution (e.g., TUPAD). Every domain entity in the system SHALL reference a tenant via `tenant_id`. The tenant model SHALL be the first table created in the database.

#### Scenario: Create a new tenant

- **WHEN** a new tenant is created with a unique `codigo` and a `nombre`
- **THEN** the tenant is persisted with an auto-generated UUID primary key
- **AND** the tenant has `created_at` and `updated_at` timestamps set to the current time
- **AND** the tenant has `deleted_at` set to NULL

#### Scenario: Tenant codigo must be unique

- **WHEN** creating a tenant with a `codigo` that already exists
- **THEN** the operation fails with a unique constraint violation error

#### Scenario: Tenant has an active/inactive state

- **WHEN** a tenant is created
- **THEN** its default `estado` is `"activo"`
- **AND** the `estado` field SHALL be restricted to values `"activo"` or `"inactivo"`

#### Scenario: Read tenant by id

- **WHEN** querying a tenant by its UUID
- **THEN** the tenant is returned with all its fields
- **AND** if the tenant does not exist, `None` is returned

#### Scenario: Soft delete a tenant

- **WHEN** a tenant is soft-deleted
- **THEN** its `deleted_at` field is set to the current timestamp
- **AND** the tenant is no longer returned by default queries (without `with_deleted`)

### Requirement: Tenant model fields

The `Tenant` model SHALL have the following columns in addition to those inherited from the base mixin:

| Column | Type | Constraints |
|--------|------|-------------|
| `nombre` | VARCHAR | NOT NULL |
| `codigo` | VARCHAR | NOT NULL, UNIQUE |
| `estado` | VARCHAR | NOT NULL, DEFAULT `'activo'`, restricted to `'activo'`/`'inactivo'` |

#### Scenario: Tenant field types and constraints

- **WHEN** a tenant record is created with `nombre`, `codigo`, and `estado`
- **THEN** the `nombre` and `codigo` fields are stored as strings
- **AND** the `codigo` is unique across all tenants
- **AND** the `estado` defaults to `"activo"` if not specified
