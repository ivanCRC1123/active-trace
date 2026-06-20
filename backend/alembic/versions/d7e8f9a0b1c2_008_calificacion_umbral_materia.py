"""008: calificacion + umbral_materia.

Revision ID: d7e8f9a0b1c2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw SQL for all DDL to avoid SQLAlchemy auto-creating enum types.

    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE origen_calificacion AS ENUM ('Importado', 'Manual'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS calificacion (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            asignacion_id   UUID NOT NULL REFERENCES asignacion(id) ON DELETE RESTRICT,
            entrada_padron_id UUID NOT NULL REFERENCES entrada_padron(id) ON DELETE RESTRICT,
            materia_id      UUID NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            actividad       VARCHAR(500) NOT NULL,
            nota_numerica   NUMERIC(10,2),
            nota_textual    VARCHAR(255),
            aprobado        BOOLEAN NOT NULL DEFAULT FALSE,
            origen          origen_calificacion NOT NULL,
            importado_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at      TIMESTAMPTZ,
            CONSTRAINT uq_calificacion_asignacion_entrada_actividad
                UNIQUE (asignacion_id, entrada_padron_id, actividad)
        )
    """))

    op.execute(sa.text(
        """
        CREATE TRIGGER trg_calificacion_updated_at
        BEFORE UPDATE ON calificacion
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    ))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_calificacion_asignacion "
        "ON calificacion (asignacion_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_calificacion_entrada_padron "
        "ON calificacion (entrada_padron_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_calificacion_materia "
        "ON calificacion (materia_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_calificacion_tenant "
        "ON calificacion (tenant_id) WHERE deleted_at IS NULL"
    ))

    # ── umbral_materia ───────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS umbral_materia (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            asignacion_id   UUID NOT NULL UNIQUE REFERENCES asignacion(id) ON DELETE RESTRICT,
            materia_id      UUID NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            umbral_pct      INTEGER NOT NULL DEFAULT 60,
            valores_aprobatorios JSONB NOT NULL DEFAULT '["Satisfactorio","Supera lo esperado"]',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at      TIMESTAMPTZ
        )
    """))

    op.execute(sa.text(
        """
        CREATE TRIGGER trg_umbral_materia_updated_at
        BEFORE UPDATE ON umbral_materia
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    ))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_umbral_materia_asignacion "
        "ON umbral_materia (asignacion_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_umbral_materia_materia "
        "ON umbral_materia (materia_id) WHERE deleted_at IS NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_umbral_materia_updated_at ON umbral_materia"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_calificacion_updated_at ON calificacion"))
    op.execute(sa.text("DROP TABLE IF EXISTS umbral_materia"))
    op.execute(sa.text("DROP TABLE IF EXISTS calificacion"))
    op.execute(sa.text("DROP TYPE IF EXISTS origen_calificacion"))
