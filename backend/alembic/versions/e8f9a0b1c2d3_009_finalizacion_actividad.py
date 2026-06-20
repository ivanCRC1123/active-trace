"""009_finalizacion_actividad — C-11 analisis-atrasados-reportes.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS finalizacion_actividad (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id   UUID        NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            entrada_padron_id UUID  NOT NULL REFERENCES entrada_padron(id) ON DELETE RESTRICT,
            materia_id  UUID        NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            asignacion_id UUID      NOT NULL REFERENCES asignacion(id) ON DELETE RESTRICT,
            actividad   VARCHAR(500) NOT NULL,
            finalizado  BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            CONSTRAINT pk_finalizacion_actividad PRIMARY KEY (id)
        )
    """))

    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION set_finalizacion_actividad_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_finalizacion_actividad_updated_at
        BEFORE UPDATE ON finalizacion_actividad
        FOR EACH ROW EXECUTE FUNCTION set_finalizacion_actividad_updated_at()
    """))

    # Unicidad: un alumno × actividad × asignacion (permite re-importar via soft-delete + insert)
    op.execute(sa.text("""
        CREATE UNIQUE INDEX uq_finalizacion_entrada_actividad_asignacion
            ON finalizacion_actividad (entrada_padron_id, actividad, asignacion_id)
            WHERE deleted_at IS NULL
    """))

    # Para cruce con calificacion (RN-07/08): finalizado=TRUE + materia + asignacion
    op.execute(sa.text("""
        CREATE INDEX idx_finalizacion_materia_asignacion
            ON finalizacion_actividad (tenant_id, materia_id, asignacion_id)
            WHERE deleted_at IS NULL AND finalizado = TRUE
    """))

    op.execute(sa.text("""
        CREATE INDEX idx_finalizacion_entrada_padron
            ON finalizacion_actividad (entrada_padron_id)
            WHERE deleted_at IS NULL
    """))

    op.execute(sa.text("""
        CREATE INDEX idx_finalizacion_tenant
            ON finalizacion_actividad (tenant_id)
            WHERE deleted_at IS NULL
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS finalizacion_actividad CASCADE"))
    op.execute(sa.text(
        "DROP FUNCTION IF EXISTS set_finalizacion_actividad_updated_at() CASCADE"
    ))
