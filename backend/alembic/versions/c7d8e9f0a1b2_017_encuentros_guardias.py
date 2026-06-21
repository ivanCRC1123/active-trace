"""017_encuentros_guardias — C-13 épica 6 (F6.1–F6.6).

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-06-21

Creates:
  - slot_encuentro      (E9 — slot recurrente o único, genera instancias)
  - instancia_encuentro (E10 — instancia puntual, estado independiente, RN-14)
  - guardia             (E11 + D-C13-6: campo fecha DATE para instancia inequívoca)

D-C13-6: campo `fecha DATE nullable` agregado a E11 (no está en la KB).
         Permite distinguir guardias de semanas distintas y consultas por rango.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── slot_encuentro (E9) ──────────────────────────────────────────────────
    op.create_table(
        "slot_encuentro",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("asignacion_id", sa.UUID(), nullable=False),
        sa.Column("materia_id", sa.UUID(), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("hora", sa.Time(timezone=False), nullable=False),
        sa.Column("dia_semana", sa.String(20), nullable=True),          # solo recurrente
        sa.Column("fecha_inicio", sa.Date(), nullable=True),             # solo recurrente
        sa.Column("cant_semanas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fecha_unica", sa.Date(), nullable=True),              # solo único
        sa.Column("meet_url", sa.Text(), nullable=True),
        sa.Column("vig_desde", sa.Date(), nullable=True),
        sa.Column("vig_hasta", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asignacion_id"], ["asignacion.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["materia_id"], ["materia.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_slot_tenant", "slot_encuentro", ["tenant_id"])
    op.create_index("ix_slot_tenant_materia", "slot_encuentro", ["tenant_id", "materia_id"])
    op.create_index("ix_slot_tenant_asignacion", "slot_encuentro", ["tenant_id", "asignacion_id"])

    # ── instancia_encuentro (E10) ────────────────────────────────────────────
    op.create_table(
        "instancia_encuentro",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("slot_id", sa.UUID(), nullable=True),   # nullable: instancias standalone futuras
        sa.Column("asignacion_id", sa.UUID(), nullable=False),  # denormalizado — siempre poblado
        sa.Column("materia_id", sa.UUID(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("hora", sa.Time(timezone=False), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="Programado"),
        sa.Column("meet_url", sa.Text(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_id"], ["slot_encuentro.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asignacion_id"], ["asignacion.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["materia_id"], ["materia.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estado IN ('Programado','Realizado','Cancelado')", name="ck_instancia_estado"),
    )
    op.create_index("ix_instancia_tenant", "instancia_encuentro", ["tenant_id"])
    op.create_index("ix_instancia_tenant_materia", "instancia_encuentro", ["tenant_id", "materia_id"])
    op.create_index("ix_instancia_tenant_asignacion", "instancia_encuentro", ["tenant_id", "asignacion_id"])
    op.create_index("ix_instancia_fecha_estado", "instancia_encuentro", ["fecha", "estado"])
    op.create_index("ix_instancia_slot", "instancia_encuentro", ["slot_id"])

    # ── guardia (E11 + D-C13-6) ─────────────────────────────────────────────
    op.create_table(
        "guardia",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("asignacion_id", sa.UUID(), nullable=False),
        sa.Column("materia_id", sa.UUID(), nullable=False),
        sa.Column("carrera_id", sa.UUID(), nullable=True),
        sa.Column("cohorte_id", sa.UUID(), nullable=True),
        sa.Column("dia", sa.String(20), nullable=False),     # Lunes..Domingo (E11)
        sa.Column("fecha", sa.Date(), nullable=True),         # D-C13-6: instancia inequívoca
        sa.Column("horario", sa.String(50), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="Pendiente"),
        sa.Column("comentarios", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asignacion_id"], ["asignacion.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["materia_id"], ["materia.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["carrera_id"], ["carrera.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cohorte_id"], ["cohorte.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estado IN ('Pendiente','Realizada','Cancelada')", name="ck_guardia_estado"),
    )
    op.create_index("ix_guardia_tenant", "guardia", ["tenant_id"])
    op.create_index("ix_guardia_tenant_asignacion", "guardia", ["tenant_id", "asignacion_id"])
    op.create_index("ix_guardia_tenant_materia", "guardia", ["tenant_id", "materia_id"])
    op.create_index("ix_guardia_fecha", "guardia", ["fecha"])


def downgrade() -> None:
    op.drop_table("guardia")
    op.drop_table("instancia_encuentro")
    op.drop_table("slot_encuentro")
