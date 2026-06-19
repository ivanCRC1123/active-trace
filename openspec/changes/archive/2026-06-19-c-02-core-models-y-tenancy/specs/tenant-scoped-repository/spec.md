## ADDED Requirements

### Requirement: Generic base repository with mandatory tenant scope

The system SHALL provide a generic `BaseRepository[ModelT]` class that implements CRUD operations with an **always-active tenant scope**. The `tenant_id` SHALL be injected at construction time and applied to every query automatically. No public method SHALL allow querying without the tenant filter.

#### Scenario: Repository requires tenant_id at construction

- **WHEN** a `BaseRepository` is instantiated
- **THEN** it requires an `AsyncSession` and a `tenant_id` (UUID) as constructor parameters
- **AND** all subsequent queries filter by that `tenant_id`

#### Scenario: List returns only active records for current tenant

- **WHEN** `list()` is called on a repository scoped to tenant A
- **THEN** it returns only records with matching `tenant_id` and `deleted_at IS NULL`
- **AND** it excludes records belonging to tenant B
- **AND** it excludes soft-deleted records

#### Scenario: Get by id returns record only if it belongs to the tenant

- **WHEN** `get_by_id(id)` is called
- **THEN** it returns the record only if its `tenant_id` matches the repository's scoped tenant
- **AND** the record is not soft-deleted (unless overridden)
- **AND** it returns `None` if the record belongs to a different tenant

#### Scenario: Create assigns tenant_id automatically

- **WHEN** `create(data)` is called
- **THEN** the `tenant_id` from the repository is assigned to the new record
- **AND** the record is persisted with a flush
- **AND** the created record is returned with its generated UUID and timestamps

#### Scenario: Update modifies only tenant-scoped records

- **WHEN** `update(id, data)` is called
- **THEN** it updates the record only if its `tenant_id` matches the repository's scoped tenant
- **AND** it returns the updated record
- **AND** it returns `None` if no matching record exists

#### Scenario: Soft delete sets deleted_at

- **WHEN** `soft_delete(id)` is called
- **THEN** the record's `deleted_at` is set to the current timestamp
- **AND** returns `True`
- **AND** returns `False` if the record does not exist or belongs to another tenant

#### Scenario: Soft-deleted records are excluded from list

- **WHEN** a record is soft-deleted
- **THEN** it is no longer returned by `list()`
- **AND** it IS returned by `list_with_deleted()`

#### Scenario: No hard delete method is exposed

- **WHEN** inspecting the `BaseRepository` class
- **THEN** there is no `hard_delete`, `delete`, or `purge` method
- **AND** the only deletion mechanism is `soft_delete`

### Requirement: Multi-tenant isolation (critical)

The system MUST guarantee that data from one tenant is never visible to another tenant through the repository layer. This is a **critical security requirement** (ADR-002).

#### Scenario: Tenant A cannot see Tenant B data

- **WHEN** two tenants exist (A and B) each with their own records
- **WHEN** a repository scoped to tenant A calls `list()`
- **THEN** it returns only tenant A's records
- **AND** it does NOT include any record belonging to tenant B

#### Scenario: Cross-tenant create never leaks tenant_id

- **WHEN** a repository scoped to tenant A creates a record
- **THEN** the record's `tenant_id` is set to tenant A's UUID
- **AND** a repository scoped to tenant B cannot see it via `list()`, `get_by_id()`, or any other query method
