"""007: version_padron + entrada_padron + materia.moodle_course_id.

Revision ID: a1b2c3d4e5f6
Revises: c6d7e8f9a0b1
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── materia: campo para trazabilidad con Moodle ───────────────────────────
    op.add_column(
        "materia",
        sa.Column("moodle_course_id", sa.String(100), nullable=True),
    )

    # ── version_padron ────────────────────────────────────────────────────────
    op.create_table(
        "version_padron",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "materia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materia.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "cohorte_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cohorte.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "cargado_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "cargado_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "activa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_version_padron_updated_at
            BEFORE UPDATE ON version_padron
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
            """
        )
    )

    # Índice único parcial: solo una versión activa por (tenant, materia, cohorte)
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_version_padron_activa
            ON version_padron (tenant_id, materia_id, cohorte_id)
            WHERE activa = TRUE AND deleted_at IS NULL
            """
        )
    )

    op.create_index(
        "idx_version_padron_materia",
        "version_padron",
        ["materia_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_version_padron_cohorte",
        "version_padron",
        ["cohorte_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_version_padron_tenant",
        "version_padron",
        ["tenant_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── entrada_padron ────────────────────────────────────────────────────────
    op.create_table(
        "entrada_padron",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("version_padron.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("apellidos", sa.String(255), nullable=False),
        sa.Column("email_cifrado", sa.Text(), nullable=False),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("comision", sa.String(255), nullable=True),
        sa.Column("regional", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_entrada_padron_updated_at
            BEFORE UPDATE ON entrada_padron
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
            """
        )
    )

    op.create_index(
        "idx_entrada_padron_version",
        "entrada_padron",
        ["version_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_entrada_padron_email_hash",
        "entrada_padron",
        ["tenant_id", "email_hash"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_entrada_padron_usuario",
        "entrada_padron",
        ["usuario_id"],
        postgresql_where=sa.text("deleted_at IS NULL AND usuario_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("entrada_padron")
    op.drop_table("version_padron")
    op.drop_column("materia", "moodle_course_id")
