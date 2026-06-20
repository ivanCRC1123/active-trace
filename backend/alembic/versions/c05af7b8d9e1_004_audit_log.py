"""004_audit_log

Create audit_log table with DB-level append-only enforcement (PostgreSQL RULEs).

Revision ID: c05af7b8d9e1
Revises: 8730994b28f2
Create Date: 2026-06-19 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c05af7b8d9e1"
down_revision: str | None = "8730994b28f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create audit_log table with indexes and append-only PostgreSQL RULEs."""

    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "fecha_hora",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("impersonado_id", sa.UUID(), nullable=True),
        sa.Column("materia_id", sa.UUID(), nullable=True),
        sa.Column("accion", sa.VARCHAR(length=100), nullable=False),
        sa.Column("detalle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "filas_afectadas",
            sa.INTEGER(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("ip", sa.VARCHAR(length=45), nullable=True),
        sa.Column("user_agent", sa.TEXT(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("audit_log_pkey")),
        # No FK constraints on tenant_id, actor_id, or impersonado_id.
        # Any cascade action (CASCADE, RESTRICT, SET NULL) conflicts with the
        # append-only RULEs added below — PostgreSQL RULEs intercept the internal
        # queries the FK mechanism uses for enforcement.
        # All UUIDs are validated at insertion time by AuditService.
    )

    op.create_index("idx_audit_log_tenant", "audit_log", ["tenant_id"])
    op.create_index("idx_audit_log_actor", "audit_log", ["actor_id"])
    op.create_index("idx_audit_log_accion", "audit_log", ["accion"])
    op.create_index(
        "idx_audit_log_fecha",
        "audit_log",
        [sa.text("fecha_hora DESC")],
    )

    # DB-level append-only enforcement.
    # DO INSTEAD NOTHING silently swallows UPDATE/DELETE (returns 0 rows affected, no error).
    # This protects the table even when accessed directly via psql or other clients.
    op.execute(
        "CREATE RULE no_update_audit_log AS ON UPDATE TO audit_log DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE no_delete_audit_log AS ON DELETE TO audit_log DO INSTEAD NOTHING"
    )


def downgrade() -> None:
    """Drop PostgreSQL RULEs then drop audit_log table."""

    op.execute("DROP RULE IF EXISTS no_update_audit_log ON audit_log")
    op.execute("DROP RULE IF EXISTS no_delete_audit_log ON audit_log")

    op.drop_index("idx_audit_log_fecha", table_name="audit_log")
    op.drop_index("idx_audit_log_accion", table_name="audit_log")
    op.drop_index("idx_audit_log_actor", table_name="audit_log")
    op.drop_index("idx_audit_log_tenant", table_name="audit_log")

    op.drop_table("audit_log")
