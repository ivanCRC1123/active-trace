"""010_comunicacion — C-12 comunicaciones-cola-worker.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Nueva columna en tenant: aprobación configurable por tenant (RN-17).
    op.execute(sa.text(
        "ALTER TABLE tenant "
        "ADD COLUMN IF NOT EXISTS requiere_aprobacion_comunicacion BOOLEAN NOT NULL DEFAULT TRUE"
    ))

    # 2. Tabla comunicacion (E21 + extensiones aprobadas en C-12).
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS comunicacion (
            id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id           UUID        NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            enviado_por         UUID        NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
            materia_id          UUID        NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            entrada_padron_id   UUID        REFERENCES entrada_padron(id) ON DELETE SET NULL,
            destinatario        TEXT        NOT NULL,
            asunto              VARCHAR(500) NOT NULL,
            cuerpo              TEXT        NOT NULL,
            estado              VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
            lote_id             UUID        NOT NULL,
            aprobado_por        UUID        REFERENCES "user"(id) ON DELETE SET NULL,
            aprobado_at         TIMESTAMPTZ,
            enviado_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ,
            CONSTRAINT pk_comunicacion PRIMARY KEY (id),
            CONSTRAINT chk_comunicacion_estado CHECK (
                estado IN ('PENDIENTE','ENVIANDO','ENVIADO','ERROR','CANCELADO')
            )
        )
    """))

    # trigger updated_at
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION set_comunicacion_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_comunicacion_updated_at
        BEFORE UPDATE ON comunicacion
        FOR EACH ROW EXECUTE FUNCTION set_comunicacion_updated_at()
    """))

    # Índices: worker (estado), panel (tenant+enviado_por), lote (tenant+lote_id)
    op.execute(sa.text("""
        CREATE INDEX idx_comunicacion_estado
            ON comunicacion (tenant_id, estado)
            WHERE deleted_at IS NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX idx_comunicacion_enviado_por
            ON comunicacion (tenant_id, enviado_por)
            WHERE deleted_at IS NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX idx_comunicacion_lote
            ON comunicacion (tenant_id, lote_id)
            WHERE deleted_at IS NULL
    """))
    # El worker necesita ENVIANDO cross-tenant — índice sin filtro tenant
    op.execute(sa.text("""
        CREATE INDEX idx_comunicacion_enviando_worker
            ON comunicacion (estado)
            WHERE deleted_at IS NULL AND estado = 'ENVIANDO'
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS comunicacion CASCADE"))
    op.execute(sa.text(
        "DROP FUNCTION IF EXISTS set_comunicacion_updated_at() CASCADE"
    ))
    op.execute(sa.text(
        "ALTER TABLE tenant "
        "DROP COLUMN IF EXISTS requiere_aprobacion_comunicacion"
    ))
