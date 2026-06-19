## ADDED Requirements

### Requirement: Base entity mixin provides common columns for all domain models

The system SHALL provide a composable mixin hierarchy that all domain entities inherit. The base mixin `BaseEntityMixin` SHALL combine timestamps, soft delete, and tenant scoping. Individual mixins (`TimeStampedMixin`, `SoftDeleteMixin`, `TenantScopedMixin`) SHALL also be available for models that need a subset of these features.

#### Scenario: TimeStampedMixin provides id, created_at, updated_at

- **WHEN** a model inherits `TimeStampedMixin`
- **THEN** it has an `id` column of type UUID with a server-side default (`gen_random_uuid()`)
- **AND** a `created_at` column of type `TIMESTAMPTZ` with server default `NOW()`
- **AND** an `updated_at` column of type `TIMESTAMPTZ` with server default `NOW()`

#### Scenario: created_at is set on insert

- **WHEN** a new record is inserted
- **THEN** `created_at` is automatically set to the current timestamp by the database

#### Scenario: updated_at is updated on every row modification

- **WHEN** a record is modified (any column changed)
- **THEN** `updated_at` is automatically updated to the current timestamp by a database trigger

#### Scenario: SoftDeleteMixin provides deleted_at

- **WHEN** a model inherits `SoftDeleteMixin`
- **THEN** it has a `deleted_at` column of type `TIMESTAMPTZ` that is nullable
- **AND** the default value is NULL

#### Scenario: Soft-deleted record has non-null deleted_at

- **WHEN** a record is soft-deleted
- **THEN** its `deleted_at` column is set to the current timestamp

#### Scenario: TenantScopedMixin provides tenant_id

- **WHEN** a model inherits `TenantScopedMixin`
- **THEN** it has a `tenant_id` column of type UUID with a NOT NULL constraint
- **AND** `tenant_id` is a foreign key referencing `tenant.id`

#### Scenario: BaseEntityMixin combines all three mixins

- **WHEN** a model inherits `BaseEntityMixin`
- **THEN** it has `id`, `tenant_id`, `created_at`, `updated_at`, and `deleted_at` columns
- **AND** all constraints and defaults from the individual mixins apply

### Requirement: UUID primary key uses gen_random_uuid()

The system SHALL use PostgreSQL's `gen_random_uuid()` function as the server-side default for all UUID primary keys. The `pgcrypto` extension SHALL be enabled in the database to support this.

#### Scenario: UUID is auto-generated on insert

- **WHEN** a record is inserted without specifying an `id`
- **THEN** the database auto-generates a UUID v4 value for the `id` column
