"""016_mensajeria_interna — C-20 mensajería interna (F11.2).

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-21

Creates:
  - hilo_mensaje      (E-C20-1 — thread header, tenant-scoped, soft-delete)
  - hilo_participante (E-C20-2 — join: hilo × usuario, ultimo_leido_at)
  - mensaje_interno   (E-C20-3 — message body, remitente_id nullable for system)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── hilo_mensaje ─────────────────────────────────────────────────────────
    op.create_table(
        "hilo_mensaje",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("asunto", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_hilo_tenant", "hilo_mensaje", ["tenant_id"])
    op.create_index("idx_hilo_tenant_active", "hilo_mensaje", ["tenant_id", "deleted_at"])

    # ── hilo_participante ─────────────────────────────────────────────────────
    op.create_table(
        "hilo_participante",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("hilo_id", sa.UUID(), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("ultimo_leido_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hilo_id"], ["hilo_mensaje.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hilo_id", "usuario_id", name="uq_hilo_participante"),
    )
    op.create_index("idx_hilo_participante_hilo", "hilo_participante", ["hilo_id"])
    op.create_index("idx_hilo_participante_usuario", "hilo_participante", ["tenant_id", "usuario_id"])

    # ── mensaje_interno ───────────────────────────────────────────────────────
    op.create_table(
        "mensaje_interno",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("hilo_id", sa.UUID(), nullable=False),
        sa.Column("remitente_id", sa.UUID(), nullable=True),   # NULL = mensaje del sistema
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hilo_id"], ["hilo_mensaje.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["remitente_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_mensaje_hilo", "mensaje_interno", ["hilo_id", "created_at"])
    op.create_index("idx_mensaje_tenant", "mensaje_interno", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("mensaje_interno")
    op.drop_table("hilo_participante")
    op.drop_table("hilo_mensaje")
