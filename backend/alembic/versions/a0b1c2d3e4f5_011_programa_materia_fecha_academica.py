"""011_programa_materia_fecha_academica — C-17 programas-y-fechas-academicas.

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Postgres ENUM tipo_evaluacion (checkfirst so C-14 can reuse with create_type=False)
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE tipo_evaluacion AS ENUM ('Parcial', 'TP', 'Coloquio', 'Recuperatorio'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))

    # 2. programa_materia (E16)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS programa_materia (
            id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id           UUID        NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            materia_id          UUID        NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            carrera_id          UUID        NOT NULL REFERENCES carrera(id) ON DELETE RESTRICT,
            cohorte_id          UUID        NOT NULL REFERENCES cohorte(id) ON DELETE RESTRICT,
            titulo              VARCHAR(255) NOT NULL,
            referencia_archivo  TEXT        NOT NULL,
            cargado_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ,
            CONSTRAINT pk_programa_materia PRIMARY KEY (id),
            CONSTRAINT uq_programa_materia_tenant_materia_carrera_cohorte
                UNIQUE (tenant_id, materia_id, carrera_id, cohorte_id)
        )
    """))

    # 3. fecha_academica (E15)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS fecha_academica (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id   UUID        NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            materia_id  UUID        NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            cohorte_id  UUID        NOT NULL REFERENCES cohorte(id) ON DELETE RESTRICT,
            tipo        tipo_evaluacion NOT NULL,
            numero      INTEGER     NOT NULL,
            periodo     VARCHAR(20) NOT NULL,
            fecha       DATE        NOT NULL,
            titulo      VARCHAR(255) NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            CONSTRAINT pk_fecha_academica PRIMARY KEY (id),
            CONSTRAINT uq_fecha_academica_instancia
                UNIQUE (tenant_id, materia_id, cohorte_id, tipo, numero, periodo)
        )
    """))

    # 4. Indexes
    op.execute(sa.text("""
        CREATE INDEX idx_programa_materia_tenant
            ON programa_materia (tenant_id)
            WHERE deleted_at IS NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX idx_programa_materia_materia_cohorte
            ON programa_materia (tenant_id, materia_id, cohorte_id)
            WHERE deleted_at IS NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX idx_fecha_academica_tenant
            ON fecha_academica (tenant_id)
            WHERE deleted_at IS NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX idx_fecha_academica_materia_cohorte
            ON fecha_academica (tenant_id, materia_id, cohorte_id)
            WHERE deleted_at IS NULL
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_fecha_academica_materia_cohorte"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_fecha_academica_tenant"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_programa_materia_materia_cohorte"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_programa_materia_tenant"))
    op.execute(sa.text("DROP TABLE IF EXISTS fecha_academica"))
    op.execute(sa.text("DROP TABLE IF EXISTS programa_materia"))
    op.execute(sa.text("DROP TYPE IF EXISTS tipo_evaluacion"))
