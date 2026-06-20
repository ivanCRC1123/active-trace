## ADDED Requirements

### Requirement: Carrera catalog per tenant

Each tenant has an isolated catalog of academic programs (`Carrera`). Carreras are identified within a tenant by a short code (`codigo`). The code must be unique within the tenant but may repeat across different tenants.

#### Scenario: Creating a Carrera with a unique code succeeds
- **WHEN** an ADMIN posts `{"codigo": "TUPAD", "nombre": "Tecnicatura Universitaria en Programación Avanzada"}` to `POST /api/v1/admin/carreras`
- **THEN** the response SHALL be HTTP 201 with `{"id": <uuid>, "tenant_id": <actor_tenant>, "codigo": "TUPAD", "nombre": "Tecnicatura Universitaria en Programación Avanzada", "estado": "Activa", "created_at": ..., "updated_at": ...}`

#### Scenario: Creating a Carrera with a duplicate code within the same tenant returns 409
- **WHEN** an ADMIN posts `{"codigo": "TUPAD", "nombre": "..."}` and a non-deleted Carrera with `codigo="TUPAD"` already exists in the same tenant
- **THEN** the response SHALL be HTTP 409

#### Scenario: Duplicate code in a different tenant is allowed
- **WHEN** two different tenants each have an ADMIN that posts `{"codigo": "TUPAD", "nombre": "..."}` independently
- **THEN** both SHALL receive HTTP 201 — tenant isolation guarantees no collision across tenants

#### Scenario: Listing Carreras returns only the actor's tenant records
- **WHEN** an ADMIN calls `GET /api/v1/admin/carreras`
- **THEN** the response SHALL contain only Carreras belonging to the actor's `tenant_id`
- **AND** no Carreras from other tenants SHALL appear, even if they exist in the database

#### Scenario: Getting a Carrera from another tenant returns 404
- **WHEN** an ADMIN calls `GET /api/v1/admin/carreras/{id}` with an `id` that belongs to a different tenant
- **THEN** the response SHALL be HTTP 404

### Requirement: Carrera soft-delete (append-only history)

Deleting a Carrera sets `deleted_at` (soft delete) and hides the record from normal reads. The physical row is never deleted.

#### Scenario: Soft-deleting a Carrera returns 204 and hides the record
- **WHEN** an ADMIN calls `DELETE /api/v1/admin/carreras/{id}` for an existing Carrera
- **THEN** the response SHALL be HTTP 204 (no body)
- **AND** a subsequent `GET /api/v1/admin/carreras/{id}` SHALL return HTTP 404
- **AND** the row SHALL still exist in the `carrera` table with `deleted_at` set

#### Scenario: Listing Carreras excludes soft-deleted records
- **WHEN** an ADMIN calls `GET /api/v1/admin/carreras`
- **THEN** Carreras with `deleted_at IS NOT NULL` SHALL NOT appear in the response

### Requirement: Carrera estado (Activa / Inactiva)

#### Scenario: Newly created Carrera has estado=Activa by default
- **WHEN** an ADMIN creates a Carrera without specifying `estado`
- **THEN** the response SHALL include `"estado": "Activa"`

#### Scenario: Updating a Carrera's estado to Inactiva
- **WHEN** an ADMIN calls `PATCH /api/v1/admin/carreras/{id}` with `{"estado": "Inactiva"}`
- **THEN** the response SHALL include `"estado": "Inactiva"`

#### Scenario: Inactiva Carrera still appears in list (estado ≠ soft-delete)
- **WHEN** an ADMIN calls `GET /api/v1/admin/carreras`
- **THEN** Carreras with `estado=Inactiva` SHALL appear in the list (they are not soft-deleted)
