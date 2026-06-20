## ADDED Requirements

### Requirement: AuditLog table is append-only and tenant-scoped

The system SHALL provide an `audit_log` table that stores immutable audit events. The table SHALL be tenant-scoped (every row has `tenant_id`), SHALL NOT have `updated_at` or `deleted_at` columns, and SHALL be protected at the database level against any UPDATE or DELETE operation.

#### Scenario: Migration creates the audit_log table
- **WHEN** migration 004 is applied
- **THEN** there SHALL be an `audit_log` table with columns: `id` (UUID PK, gen_random_uuid()), `tenant_id` (UUID NOT NULL FK → tenant.id ON DELETE CASCADE), `fecha_hora` (TIMESTAMPTZ NOT NULL DEFAULT now()), `actor_id` (UUID NOT NULL FK → user.id ON DELETE RESTRICT), `impersonado_id` (UUID NULLABLE FK → user.id ON DELETE SET NULL), `materia_id` (UUID NULLABLE, no FK constraint), `accion` (VARCHAR(100) NOT NULL), `detalle` (JSONB NULLABLE), `filas_afectadas` (INTEGER NOT NULL DEFAULT 0), `ip` (VARCHAR(45) NULLABLE), `user_agent` (TEXT NULLABLE)
- **AND** there SHALL be indexes named `idx_audit_log_tenant` on `(tenant_id)`, `idx_audit_log_actor` on `(actor_id)`, `idx_audit_log_accion` on `(accion)`, `idx_audit_log_fecha` on `(fecha_hora DESC)`
- **AND** there SHALL be NO `updated_at` or `deleted_at` columns

#### Scenario: Database-level RULE prevents UPDATE
- **WHEN** a direct SQL `UPDATE audit_log SET accion = 'TAMPERED' WHERE id = :id` is executed against PostgreSQL
- **THEN** the statement SHALL complete without raising an error
- **AND** the statement SHALL affect 0 rows (RULE: DO INSTEAD NOTHING)
- **AND** the original row SHALL remain unchanged

#### Scenario: Database-level RULE prevents DELETE
- **WHEN** a direct SQL `DELETE FROM audit_log WHERE id = :id` is executed
- **THEN** the statement SHALL complete without raising an error
- **AND** the statement SHALL affect 0 rows
- **AND** the original row SHALL still exist

#### Scenario: Migration downgrades cleanly
- **WHEN** `alembic downgrade -1` is run after `alembic upgrade head`
- **THEN** the PostgreSQL RULEs SHALL be dropped before the table
- **AND** the `audit_log` table SHALL be dropped without error
- **AND** running `alembic upgrade head` again SHALL recreate the table and RULEs successfully

---

### Requirement: Action codes catalog

The system SHALL provide a Python module `app/core/audit_codes.py` with string constants for all recognized audit action codes. These constants are the single source of truth for `accion` values written to `audit_log`.

#### Scenario: C-05 action codes are importable
- **WHEN** `from app.core.audit_codes import IMPERSONACION_INICIAR, IMPERSONACION_FINALIZAR` is imported
- **THEN** `IMPERSONACION_INICIAR == "IMPERSONACION_INICIAR"` SHALL be True
- **AND** `IMPERSONACION_FINALIZAR == "IMPERSONACION_FINALIZAR"` SHALL be True

#### Scenario: Future module codes are stubbed and importable
- **WHEN** the `app.core.audit_codes` module is imported
- **THEN** constants `CALIFICACIONES_IMPORTAR`, `PADRON_CARGAR`, `COMUNICACION_ENVIAR`, `ASIGNACION_MODIFICAR`, `LIQUIDACION_CERRAR` SHALL be defined and equal to their respective string names
