## ADDED Requirements

### Requirement: Single Materia catalog per tenant (ADR-006)

`Materia` is the unique source of truth for academic subjects within a tenant. The same subject can be taught across multiple Carreras and Cohortes via future Dictado/Asignacion relationships (C-07+). The `codigo` must be unique within the tenant.

#### Scenario: Creating a Materia with a unique code succeeds
- **WHEN** an ADMIN posts `{"codigo": "PROG_I", "nombre": "Programación I"}` to `POST /api/v1/admin/materias`
- **THEN** the response SHALL be HTTP 201 with `{"id": ..., "tenant_id": ..., "codigo": "PROG_I", "nombre": "Programación I", "estado": "Activa", "created_at": ..., "updated_at": ...}`

#### Scenario: Duplicate codigo within the same tenant returns 409
- **WHEN** a Materia with `codigo="PROG_I"` already exists (non-deleted) in the tenant
- **AND** an ADMIN posts another Materia with `codigo="PROG_I"`
- **THEN** the response SHALL be HTTP 409

#### Scenario: Same codigo in a different tenant is allowed
- **WHEN** two different tenants each have a Materia with `codigo="PROG_I"`
- **THEN** both SHALL be valid — tenant isolation applies to uniqueness

#### Scenario: Listing Materias returns only the actor's tenant records
- **WHEN** an ADMIN calls `GET /api/v1/admin/materias`
- **THEN** the response SHALL contain only Materias with the actor's `tenant_id`
- **AND** Materias from other tenants SHALL NOT appear

#### Scenario: Getting a Materia from another tenant returns 404
- **WHEN** an ADMIN calls `GET /api/v1/admin/materias/{id}` with an id from a different tenant
- **THEN** the response SHALL be HTTP 404

### Requirement: Materia soft-delete and estado

#### Scenario: Soft-deleting a Materia hides it from normal reads
- **WHEN** an ADMIN calls `DELETE /api/v1/admin/materias/{id}`
- **THEN** the response SHALL be HTTP 204
- **AND** `GET /api/v1/admin/materias/{id}` SHALL return HTTP 404
- **AND** the row SHALL still exist with `deleted_at` set

#### Scenario: Materia with estado=Inactiva still appears in list
- **WHEN** a Materia has `estado="Inactiva"` but `deleted_at IS NULL`
- **AND** an ADMIN calls `GET /api/v1/admin/materias`
- **THEN** the Materia SHALL appear in the response with `"estado": "Inactiva"`
- **AND** `estado="Inactiva"` SHALL NOT be treated as soft-deleted

#### Scenario: Updating a Materia's nombre and estado
- **WHEN** an ADMIN calls `PATCH /api/v1/admin/materias/{id}` with `{"nombre": "Programación I — Python", "estado": "Inactiva"}`
- **THEN** the response SHALL reflect the updated values
