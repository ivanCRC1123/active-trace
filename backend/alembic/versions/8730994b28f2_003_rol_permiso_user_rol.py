"""003_rol_permiso_user_rol

Create rol, permiso, rol_permiso, and user_rol tables for RBAC.

Revision ID: 8730994b28f2
Revises: a2b3c4d5e6f7
Create Date: 2026-06-19 05:55:15.476240
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8730994b28f2"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create rol, permiso, rol_permiso, and user_rol tables."""

    # ── 1. rol table ──────────────────────────────────────────────
    op.create_table(
        "rol",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.VARCHAR(length=50), nullable=False),
        sa.Column("descripcion", sa.VARCHAR(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("rol_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("rol_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "nombre", name=op.f("uq_rol_tenant_nombre")),
    )

    op.execute(
        """
        CREATE TRIGGER trg_rol_updated_at
        BEFORE UPDATE ON rol
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # ── 2. permiso table ──────────────────────────────────────────
    op.create_table(
        "permiso",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.VARCHAR(length=100), nullable=False),
        sa.Column("descripcion", sa.VARCHAR(length=255), nullable=True),
        sa.Column("modulo", sa.VARCHAR(length=50), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("permiso_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("permiso_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "codigo", name=op.f("uq_permiso_tenant_codigo")),
    )

    op.execute(
        """
        CREATE TRIGGER trg_permiso_updated_at
        BEFORE UPDATE ON permiso
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # ── 3. rol_permiso table ───────────────────────────────────────
    op.create_table(
        "rol_permiso",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("rol_id", sa.UUID(), nullable=False),
        sa.Column("permiso_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.VARCHAR(length=10), nullable=False, server_default=sa.text("'all'")),
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
        sa.PrimaryKeyConstraint("id", name=op.f("rol_permiso_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("rol_permiso_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rol_id"],
            ["rol.id"],
            name=op.f("rol_permiso_rol_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permiso_id"],
            ["permiso.id"],
            name=op.f("rol_permiso_permiso_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "rol_id", "permiso_id",
            name=op.f("uq_rol_permiso_tenant_rol_permiso"),
        ),
    )

    op.execute(
        """
        CREATE TRIGGER trg_rol_permiso_updated_at
        BEFORE UPDATE ON rol_permiso
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # ── 4. user_rol table ──────────────────────────────────────────
    op.create_table(
        "user_rol",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("rol_id", sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("user_rol_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("user_rol_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("user_rol_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rol_id"],
            ["rol.id"],
            name=op.f("user_rol_rol_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "rol_id",
            name=op.f("uq_user_rol_tenant_user_rol"),
        ),
    )

    op.execute(
        """
        CREATE TRIGGER trg_user_rol_updated_at
        BEFORE UPDATE ON user_rol
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )


def downgrade() -> None:
    """Drop user_rol, rol_permiso, permiso, and rol tables."""

    op.execute("DROP TRIGGER IF EXISTS trg_user_rol_updated_at ON user_rol")
    op.execute("DROP TRIGGER IF EXISTS trg_rol_permiso_updated_at ON rol_permiso")
    op.execute("DROP TRIGGER IF EXISTS trg_permiso_updated_at ON permiso")
    op.execute("DROP TRIGGER IF EXISTS trg_rol_updated_at ON rol")

    op.drop_table("user_rol")
    op.drop_table("rol_permiso")
    op.drop_table("permiso")
    op.drop_table("rol")
