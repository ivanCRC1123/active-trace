"""018_tarea_comentario_tarea — C-16 tareas-internas (E12).

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-21

Creates:
  - tarea             (E12 — tarea interna con FSM Pendiente/En progreso/Resuelta/Cancelada)
  - comentario_tarea  (E12 — hilo de comentarios sobre una tarea)

D-C16-6: contexto_id es UUID nullable sin FK — referencia blanda polimórfica.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tarea",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("materia_id", sa.UUID(), nullable=True),
        sa.Column("asignado_a", sa.UUID(), nullable=False),
        sa.Column("asignado_por", sa.UUID(), nullable=False),
        sa.Column(
            "estado",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'Pendiente'"),
        ),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("contexto_id", sa.UUID(), nullable=True),  # referencia blanda, sin FK
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["materia_id"], ["materia.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asignado_a"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["asignado_por"], ["user.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "estado IN ('Pendiente', 'En progreso', 'Resuelta', 'Cancelada')",
            name="ck_tarea_estado",
        ),
    )
    op.create_index("ix_tarea_tenant_id", "tarea", ["tenant_id"])
    op.create_index("ix_tarea_tenant_asignado_a", "tarea", ["tenant_id", "asignado_a"])
    op.create_index("ix_tarea_tenant_asignado_por", "tarea", ["tenant_id", "asignado_por"])
    op.create_index("ix_tarea_tenant_estado", "tarea", ["tenant_id", "estado"])

    op.create_table(
        "comentario_tarea",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("tarea_id", sa.UUID(), nullable=False),
        sa.Column("autor_id", sa.UUID(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tarea_id"], ["tarea.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["autor_id"], ["user.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_comentario_tarea_tarea_id", "comentario_tarea", ["tarea_id"])
    op.create_index("ix_comentario_tarea_tenant_id", "comentario_tarea", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_comentario_tarea_tenant_id", table_name="comentario_tarea")
    op.drop_index("ix_comentario_tarea_tarea_id", table_name="comentario_tarea")
    op.drop_table("comentario_tarea")

    op.drop_index("ix_tarea_tenant_estado", table_name="tarea")
    op.drop_index("ix_tarea_tenant_asignado_por", table_name="tarea")
    op.drop_index("ix_tarea_tenant_asignado_a", table_name="tarea")
    op.drop_index("ix_tarea_tenant_id", table_name="tarea")
    op.drop_table("tarea")
