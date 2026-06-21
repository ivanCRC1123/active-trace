"""014_liquidacion_honorarios — C-18 liquidaciones-y-honorarios.

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-20

Creates:
  - ENUMs: rol_liquidable, liquidacion_estado, factura_estado
  - materia_grupo      (E16a — PA-22 resolution, OD-1)
  - salario_base       (E17 — base salary per liquidable role + period)
  - salario_plus       (E18 — plus per category group × role + period)
  - liquidacion        (E19 — monthly honorarium per docente × cohorte × period)
  - factura            (E20 — invoice uploaded by facturador docente)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. ENUMs ────────────────────────────────────────────────────────────

    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE rol_liquidable AS ENUM ('PROFESOR', 'TUTOR', 'NEXO', 'COORDINADOR'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE liquidacion_estado AS ENUM ('Abierta', 'Cerrada'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE factura_estado AS ENUM ('Pendiente', 'Abonada'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    ))

    # ── 2. materia_grupo ─────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS materia_grupo (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id   UUID        NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            materia_id  UUID        NOT NULL REFERENCES materia(id) ON DELETE RESTRICT,
            grupo       VARCHAR(50) NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_materia_grupo_tenant_materia_grupo
                UNIQUE (tenant_id, materia_id, grupo)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_materia_grupo_materia "
        "ON materia_grupo (tenant_id, materia_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_materia_grupo_grupo "
        "ON materia_grupo (tenant_id, grupo) WHERE deleted_at IS NULL"
    ))

    # ── 3. salario_base ──────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS salario_base (
            id          UUID             NOT NULL DEFAULT gen_random_uuid(),
            tenant_id   UUID             NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            rol         rol_liquidable   NOT NULL,
            monto       NUMERIC(12, 2)   NOT NULL,
            desde       DATE             NOT NULL,
            hasta       DATE,
            created_at  TIMESTAMPTZ      NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ      NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_salario_base_rol "
        "ON salario_base (tenant_id, rol) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_salario_base_vigencia "
        "ON salario_base (tenant_id, rol, desde, hasta) WHERE deleted_at IS NULL"
    ))

    # ── 4. salario_plus ──────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS salario_plus (
            id          UUID             NOT NULL DEFAULT gen_random_uuid(),
            tenant_id   UUID             NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            grupo       VARCHAR(50)      NOT NULL,
            rol         rol_liquidable   NOT NULL,
            descripcion VARCHAR(255)     NOT NULL,
            monto       NUMERIC(12, 2)   NOT NULL,
            desde       DATE             NOT NULL,
            hasta       DATE,
            created_at  TIMESTAMPTZ      NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ      NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_salario_plus_grupo "
        "ON salario_plus (tenant_id, grupo) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_salario_plus_rol "
        "ON salario_plus (tenant_id, rol) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_salario_plus_vigencia "
        "ON salario_plus (tenant_id, grupo, rol, desde, hasta) WHERE deleted_at IS NULL"
    ))

    # ── 5. liquidacion ───────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS liquidacion (
            id                         UUID               NOT NULL DEFAULT gen_random_uuid(),
            tenant_id                  UUID               NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            cohorte_id                 UUID               NOT NULL REFERENCES cohorte(id) ON DELETE RESTRICT,
            periodo                    VARCHAR(7)         NOT NULL,
            usuario_id                 UUID               NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
            rol                        rol_liquidable     NOT NULL,
            comisiones                 JSON               NOT NULL DEFAULT '[]'::json,
            monto_base                 NUMERIC(12, 2)     NOT NULL,
            monto_plus                 NUMERIC(12, 2)     NOT NULL,
            total                      NUMERIC(12, 2)     NOT NULL,
            es_nexo                    BOOLEAN            NOT NULL DEFAULT FALSE,
            excluido_por_factura       BOOLEAN            NOT NULL DEFAULT FALSE,
            datos_bancarios_incompletos BOOLEAN           NOT NULL DEFAULT FALSE,
            estado                     liquidacion_estado NOT NULL DEFAULT 'Abierta',
            created_at                 TIMESTAMPTZ        NOT NULL DEFAULT now(),
            updated_at                 TIMESTAMPTZ        NOT NULL DEFAULT now(),
            deleted_at                 TIMESTAMPTZ,
            PRIMARY KEY (id),
            CONSTRAINT uq_liquidacion_docente_periodo
                UNIQUE (tenant_id, cohorte_id, usuario_id, rol, periodo)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_liquidacion_cohorte "
        "ON liquidacion (tenant_id, cohorte_id, periodo) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_liquidacion_usuario "
        "ON liquidacion (tenant_id, usuario_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_liquidacion_estado "
        "ON liquidacion (tenant_id, estado) WHERE deleted_at IS NULL"
    ))

    # ── 6. factura ───────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS factura (
            id                  UUID           NOT NULL DEFAULT gen_random_uuid(),
            tenant_id           UUID           NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            usuario_id          UUID           NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
            periodo             VARCHAR(7)     NOT NULL,
            detalle             TEXT           NOT NULL,
            referencia_archivo  TEXT           NOT NULL,
            tamano_kb           NUMERIC(12, 3) NOT NULL,
            estado              factura_estado NOT NULL DEFAULT 'Pendiente',
            cargada_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
            abonada_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ,
            PRIMARY KEY (id)
        )
    """))

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_factura_usuario "
        "ON factura (tenant_id, usuario_id) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_factura_periodo "
        "ON factura (tenant_id, periodo) WHERE deleted_at IS NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_factura_estado "
        "ON factura (tenant_id, estado) WHERE deleted_at IS NULL"
    ))


def downgrade() -> None:
    for idx in [
        "idx_factura_estado",
        "idx_factura_periodo",
        "idx_factura_usuario",
        "idx_liquidacion_estado",
        "idx_liquidacion_usuario",
        "idx_liquidacion_cohorte",
        "idx_salario_plus_vigencia",
        "idx_salario_plus_rol",
        "idx_salario_plus_grupo",
        "idx_salario_base_vigencia",
        "idx_salario_base_rol",
        "idx_materia_grupo_grupo",
        "idx_materia_grupo_materia",
    ]:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {idx}"))

    op.execute(sa.text("DROP TABLE IF EXISTS factura"))
    op.execute(sa.text("DROP TABLE IF EXISTS liquidacion"))
    op.execute(sa.text("DROP TABLE IF EXISTS salario_plus"))
    op.execute(sa.text("DROP TABLE IF EXISTS salario_base"))
    op.execute(sa.text("DROP TABLE IF EXISTS materia_grupo"))

    for typ in ("factura_estado", "liquidacion_estado", "rol_liquidable"):
        op.execute(sa.text(
            f"DO $$ BEGIN DROP TYPE IF EXISTS {typ}; "
            "EXCEPTION WHEN OTHERS THEN NULL; "
            "END $$"
        ))
