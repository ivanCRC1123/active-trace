"""012_evaluacion_reserva_resultado — C-14 evaluaciones-y-coloquios.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-06-20

Creates:
  - evaluacion (E14 convocatoria)
  - convocado_evaluacion (habilitados para una convocatoria)
  - reserva_evaluacion (reserva de turno por alumno)
  - resultado_evaluacion (nota final por alumno)

NOTE: tipo_evaluacion ENUM already exists from migration 011 (C-17).
      Do NOT create or drop it here (create_type=False in ORM).
      Only estado_reserva is new in this migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. evaluacion (E14)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS evaluacion (
            id               UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id        UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            materia_id       UUID        NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            cohorte_id       UUID        NOT NULL REFERENCES cohorte(id) ON DELETE RESTRICT,
            tipo             tipo_evaluacion NOT NULL,
            instancia        VARCHAR(255) NOT NULL,
            dias_disponibles INTEGER     NOT NULL,
            cupo_total       INTEGER     NOT NULL DEFAULT 0,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at       TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_evaluacion_instancia
                UNIQUE (tenant_id, materia_id, cohorte_id, tipo, instancia)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_evaluacion_tenant "
        "ON evaluacion (tenant_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_evaluacion_materia_cohorte "
        "ON evaluacion (tenant_id, materia_id, cohorte_id) WHERE deleted_at IS NULL"
    ))

    # 2. convocado_evaluacion (habilitados — PII: email_cifrado + email_hash)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS convocado_evaluacion (
            id             UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id      UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            evaluacion_id  UUID        NOT NULL REFERENCES evaluacion(id) ON DELETE RESTRICT,
            usuario_id     UUID        REFERENCES "user"(id) ON DELETE SET NULL,
            nombre         VARCHAR(255) NOT NULL,
            apellidos      VARCHAR(255) NOT NULL,
            email_cifrado  TEXT        NOT NULL,
            email_hash     VARCHAR(64) NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at     TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_convocado_evaluacion_usuario
                UNIQUE (tenant_id, evaluacion_id, usuario_id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_convocado_evaluacion_id "
        "ON convocado_evaluacion (tenant_id, evaluacion_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_convocado_email_hash "
        "ON convocado_evaluacion (tenant_id, evaluacion_id, email_hash) WHERE deleted_at IS NULL"
    ))

    # 3. estado_reserva ENUM (new in 012)
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE estado_reserva AS ENUM ('Activa', 'Cancelada'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))

    # 4. reserva_evaluacion
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS reserva_evaluacion (
            id            UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id     UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            evaluacion_id UUID        NOT NULL REFERENCES evaluacion(id) ON DELETE RESTRICT,
            alumno_id     UUID        NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
            fecha_hora    TIMESTAMPTZ NOT NULL,
            estado        estado_reserva NOT NULL DEFAULT 'Activa',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at    TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_reserva_evaluacion_alumno
                UNIQUE (tenant_id, evaluacion_id, alumno_id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_reserva_evaluacion_id "
        "ON reserva_evaluacion (tenant_id, evaluacion_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_reserva_alumno_id "
        "ON reserva_evaluacion (tenant_id, alumno_id) WHERE deleted_at IS NULL"
    ))

    # 5. resultado_evaluacion
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS resultado_evaluacion (
            id            UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id     UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            evaluacion_id UUID        NOT NULL REFERENCES evaluacion(id) ON DELETE RESTRICT,
            alumno_id     UUID        NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
            nota_final    VARCHAR(255) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at    TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_resultado_evaluacion_alumno
                UNIQUE (tenant_id, evaluacion_id, alumno_id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_resultado_evaluacion_id "
        "ON resultado_evaluacion (tenant_id, evaluacion_id) WHERE deleted_at IS NULL"
    ))


def downgrade() -> None:
    # Drop indexes
    for idx in [
        "idx_resultado_evaluacion_id",
        "idx_reserva_alumno_id",
        "idx_reserva_evaluacion_id",
        "idx_convocado_email_hash",
        "idx_convocado_evaluacion_id",
        "idx_evaluacion_materia_cohorte",
        "idx_evaluacion_tenant",
    ]:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {idx}"))

    # Drop tables in dependency order
    op.execute(sa.text("DROP TABLE IF EXISTS resultado_evaluacion"))
    op.execute(sa.text("DROP TABLE IF EXISTS reserva_evaluacion"))
    op.execute(sa.text("DROP TABLE IF EXISTS convocado_evaluacion"))
    op.execute(sa.text("DROP TABLE IF EXISTS evaluacion"))

    # Drop estado_reserva ENUM (only drop what 012 created)
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  DROP TYPE IF EXISTS estado_reserva; "
        "EXCEPTION WHEN OTHERS THEN NULL; "
        "END $$"
    ))
    # NOTE: tipo_evaluacion is NOT dropped here — it belongs to migration 011 (C-17).
