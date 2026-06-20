## ADDED Requirements

### Requirement: Cohorte belongs to one Carrera (per KB model E2)

Each Cohorte is scoped to a single Carrera within a tenant. The combination `(tenant_id, carrera_id, nombre)` must be unique.

#### Scenario: Creating a Cohorte for an active Carrera succeeds
- **WHEN** an ADMIN posts `{"carrera_id": <uuid>, "nombre": "AGO-2025", "anio": 2025, "vig_desde": "2025-08-01"}` to `POST /api/v1/admin/cohortes`
- **AND** `carrera_id` belongs to an active Carrera in the same tenant
- **THEN** the response SHALL be HTTP 201 with `{"id": ..., "tenant_id": ..., "carrera_id": ..., "nombre": "AGO-2025", "anio": 2025, "vig_desde": "2025-08-01", "vig_hasta": null, "estado": "Activa", ...}`

#### Scenario: Creating a Cohorte for an inactive Carrera returns 400
- **WHEN** an ADMIN posts a valid Cohorte payload but `carrera.estado == "Inactiva"`
- **THEN** the response SHALL be HTTP 400
- **AND** no Cohorte row SHALL be created

#### Scenario: Creating a Cohorte with a Carrera from another tenant returns 404
- **WHEN** an ADMIN posts a `carrera_id` that does not exist within the actor's tenant (even if it exists in another tenant's data)
- **THEN** the response SHALL be HTTP 404

#### Scenario: Duplicate nombre within the same (tenant, carrera) returns 409
- **WHEN** a Cohorte named "AGO-2025" already exists for the same tenant and carrera
- **AND** an ADMIN posts another Cohorte with the same `nombre` and `carrera_id`
- **THEN** the response SHALL be HTTP 409

#### Scenario: Same nombre is allowed across different Carreras in the same tenant
- **WHEN** Carrera A and Carrera B both have a Cohorte named "AGO-2025"
- **THEN** both SHALL be valid — the unique constraint includes `carrera_id`

### Requirement: vig_hasta is optional (open-ended cohort)

#### Scenario: Creating a Cohorte without vig_hasta is valid
- **WHEN** an ADMIN posts a Cohorte without the `vig_hasta` field
- **THEN** the response SHALL be HTTP 201 with `"vig_hasta": null`

#### Scenario: Updating a Cohorte to set vig_hasta closes it
- **WHEN** an ADMIN calls `PATCH /api/v1/admin/cohortes/{id}` with `{"vig_hasta": "2026-01-31"}`
- **THEN** the response SHALL include `"vig_hasta": "2026-01-31"`

### Requirement: Cohorte soft-delete

#### Scenario: Soft-deleting a Cohorte returns 204
- **WHEN** an ADMIN calls `DELETE /api/v1/admin/cohortes/{id}`
- **THEN** the response SHALL be HTTP 204
- **AND** a subsequent `GET /api/v1/admin/cohortes/{id}` SHALL return HTTP 404
- **AND** the physical row SHALL remain with `deleted_at` set
