## ADDED Requirements

### Requirement: RBAC — only ADMIN can manage academic structure

All endpoints under `/api/v1/admin/` (carreras, cohortes, materias) require the `estructura_academica:gestionar` permission, which is granted exclusively to the ADMIN role.

#### Scenario: Non-admin role receives 403 on any estructura endpoint
- **WHEN** a user with role PROFESOR, COORDINADOR, TUTOR, ALUMNO, NEXO, or FINANZAS calls any endpoint under `/api/v1/admin/carreras`, `/api/v1/admin/cohortes`, or `/api/v1/admin/materias`
- **THEN** the response SHALL be HTTP 403

#### Scenario: ADMIN receives 200/201/204 on all estructura endpoints
- **WHEN** a user with role ADMIN calls any of the 15 endpoints
- **THEN** the response SHALL NOT be HTTP 403 or HTTP 401

#### Scenario: Unauthenticated request receives 401
- **WHEN** a request is made without a valid JWT in the Authorization header
- **THEN** the response SHALL be HTTP 401

### Requirement: HTTP status codes

#### Scenario: Successful POST returns 201
- **WHEN** an ADMIN creates a new Carrera, Cohorte, or Materia successfully
- **THEN** the response SHALL be HTTP 201 with the created resource body

#### Scenario: Successful DELETE returns 204
- **WHEN** an ADMIN soft-deletes an existing Carrera, Cohorte, or Materia
- **THEN** the response SHALL be HTTP 204 with no body

#### Scenario: Duplicate unique key returns 409
- **WHEN** an ADMIN attempts to create a resource with a `codigo` or `nombre` that violates a unique constraint within the tenant
- **THEN** the response SHALL be HTTP 409 Conflict

#### Scenario: Resource not found returns 404
- **WHEN** an ADMIN calls GET, PATCH, or DELETE with a non-existent id (or an id from another tenant)
- **THEN** the response SHALL be HTTP 404 Not Found

#### Scenario: Business rule violation (inactive Carrera) returns 400
- **WHEN** an ADMIN attempts to create a Cohorte for a Carrera that is Inactiva
- **THEN** the response SHALL be HTTP 400 Bad Request

### Requirement: Tenant isolation on all endpoints

#### Scenario: ADMIN cannot read resources from another tenant via direct id
- **WHEN** an ADMIN with tenant A calls `GET /api/v1/admin/carreras/{id}` where `{id}` is a Carrera belonging to tenant B
- **THEN** the response SHALL be HTTP 404 (not a 403 — existence of foreign-tenant data must not be revealed)

#### Scenario: List endpoints return only the caller's tenant data
- **WHEN** an ADMIN calls any list endpoint (`GET /api/v1/admin/carreras`, `/cohortes`, `/materias`)
- **THEN** the response SHALL contain ONLY resources whose `tenant_id` matches the caller's tenant
- **AND** the total count SHALL reflect only the caller's tenant records
