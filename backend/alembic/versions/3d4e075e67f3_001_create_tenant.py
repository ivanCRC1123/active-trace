"""001_create_tenant

Create extension pgcrypto, trigger function update_updated_at_column(),
tenant table, and the updated_at trigger on the tenant table.

Revision ID: 3d4e075e67f3
Revises:
Create Date: 2026-06-19 01:48:45.945227
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3d4e075e67f3"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration — create extension, trigger function, and tenant table."""

    # 1. Enable pgcrypto for gen_random_uuid() (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 2. Create trigger function for auto-updating updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # 3. Create tenant table
    op.create_table(
        "tenant",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("nombre", sa.VARCHAR(length=255), nullable=False),
        sa.Column(
            "codigo", sa.VARCHAR(length=50), nullable=False, unique=True
        ),
        sa.Column(
            "estado",
            sa.VARCHAR(length=20),
            server_default=sa.text("'activo'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "deleted_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tenant_pkey")),
        sa.UniqueConstraint("codigo", name=op.f("tenant_codigo_key")),
    )

    # 4. Create trigger on tenant table
    op.execute(
        """
        CREATE TRIGGER trg_tenant_updated_at
        BEFORE UPDATE ON tenant
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )


def downgrade() -> None:
    """Revert the migration — drop trigger, table, and function."""

    # 1. Drop trigger on tenant table
    op.execute("DROP TRIGGER IF EXISTS trg_tenant_updated_at ON tenant")

    # 2. Drop tenant table
    op.drop_table("tenant")

    # 3. Drop trigger function (only if no other tables depend on it)
    # We use IF EXISTS to be safe.
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
