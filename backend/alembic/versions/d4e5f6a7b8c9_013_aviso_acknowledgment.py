"""013_aviso_acknowledgment — C-15 avisos-y-acknowledgment.

Revision ID: d4e5f6a7b8c9
Revises: b1c2d3e4f5a6
Create Date: 2026-06-20

Creates:
  - aviso (E13 tablón de avisos institucional)
  - acknowledgment_aviso (acuse de recibo por usuario)
  - ENUMs: alcance_aviso, severidad_aviso
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. alcance_aviso ENUM
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE alcance_aviso AS ENUM ('Global', 'PorMateria', 'PorCohorte', 'PorRol'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))

    # 2. severidad_aviso ENUM
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE severidad_aviso AS ENUM ('Info', 'Advertencia', 'Critico'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))

    # 3. aviso
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS aviso (
            id           UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id    UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            alcance      alcance_aviso NOT NULL,
            materia_id   UUID        REFERENCES materia(id) ON DELETE RESTRICT,
            cohorte_id   UUID        REFERENCES cohorte(id) ON DELETE RESTRICT,
            rol_destino  VARCHAR(50),
            severidad    severidad_aviso NOT NULL,
            titulo       VARCHAR(255) NOT NULL,
            cuerpo       TEXT        NOT NULL,
            inicio_en    TIMESTAMPTZ NOT NULL,
            fin_en       TIMESTAMPTZ NOT NULL,
            orden        INTEGER     NOT NULL DEFAULT 0,
            activo       BOOLEAN     NOT NULL DEFAULT TRUE,
            requiere_ack BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at   TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_aviso_tenant "
        "ON aviso (tenant_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_aviso_vigencia "
        "ON aviso (tenant_id, activo, inicio_en, fin_en) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_aviso_alcance "
        "ON aviso (tenant_id, alcance) WHERE deleted_at IS NULL"
    ))

    # 4. acknowledgment_aviso
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS acknowledgment_aviso (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id   UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            aviso_id    UUID        NOT NULL REFERENCES aviso(id) ON DELETE RESTRICT,
            usuario_id  UUID        NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_ack_aviso_usuario
                UNIQUE (tenant_id, aviso_id, usuario_id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_ack_aviso_id "
        "ON acknowledgment_aviso (aviso_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_ack_usuario_id "
        "ON acknowledgment_aviso (tenant_id, usuario_id) WHERE deleted_at IS NULL"
    ))


def downgrade() -> None:
    for idx in [
        "idx_ack_usuario_id",
        "idx_ack_aviso_id",
        "idx_aviso_alcance",
        "idx_aviso_vigencia",
        "idx_aviso_tenant",
    ]:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {idx}"))

    op.execute(sa.text("DROP TABLE IF EXISTS acknowledgment_aviso"))
    op.execute(sa.text("DROP TABLE IF EXISTS aviso"))

    op.execute(sa.text(
        "DO $$ BEGIN "
        "  DROP TYPE IF EXISTS severidad_aviso; "
        "EXCEPTION WHEN OTHERS THEN NULL; "
        "END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  DROP TYPE IF EXISTS alcance_aviso; "
        "EXCEPTION WHEN OTHERS THEN NULL; "
        "END $$"
    ))
