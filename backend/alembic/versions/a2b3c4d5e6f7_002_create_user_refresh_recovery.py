"""002_create_user_refresh_recovery

Create user, refresh_token, and recovery_token tables.

Revision ID: a2b3c4d5e6f7
Revises: 3d4e075e67f3
Create Date: 2026-06-19 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "3d4e075e67f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user, refresh_token, and recovery_token tables."""

    # ── 1. user table ──────────────────────────────────────────────
    op.create_table(
        "user",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.VARCHAR(length=255), nullable=False),
        sa.Column("password_hash", sa.VARCHAR(length=255), nullable=False),
        sa.Column("nombre", sa.VARCHAR(length=100), nullable=False),
        sa.Column("apellido", sa.VARCHAR(length=100), nullable=False),
        sa.Column("is_2fa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("user_pkey")),
        sa.UniqueConstraint("email", name=op.f("user_email_key")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("user_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)
    op.create_index(op.f("ix_user_tenant_id"), "user", ["tenant_id"])

    op.execute(
        """
        CREATE TRIGGER trg_user_updated_at
        BEFORE UPDATE ON "user"
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # ── 2. refresh_token table ─────────────────────────────────────
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.VARCHAR(length=64), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column(
            "expires_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("refresh_token_pkey")),
        sa.UniqueConstraint("token_hash", name=op.f("refresh_token_token_hash_key")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("refresh_token_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("refresh_token_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_refresh_token_token_hash"),
        "refresh_token",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_refresh_token_user_id"),
        "refresh_token",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_refresh_token_family_id"),
        "refresh_token",
        ["family_id"],
    )

    op.execute(
        """
        CREATE TRIGGER trg_refresh_token_updated_at
        BEFORE UPDATE ON refresh_token
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # ── 3. recovery_token table ────────────────────────────────────
    op.create_table(
        "recovery_token",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.VARCHAR(length=64), nullable=False),
        sa.Column(
            "expires_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
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
        sa.PrimaryKeyConstraint("id", name=op.f("recovery_token_pkey")),
        sa.UniqueConstraint("token_hash", name=op.f("recovery_token_token_hash_key")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("recovery_token_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("recovery_token_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_recovery_token_token_hash"),
        "recovery_token",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_recovery_token_user_id"),
        "recovery_token",
        ["user_id"],
    )

    op.execute(
        """
        CREATE TRIGGER trg_recovery_token_updated_at
        BEFORE UPDATE ON recovery_token
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )


def downgrade() -> None:
    """Drop recovery_token, refresh_token, and user tables."""

    op.execute("DROP TRIGGER IF EXISTS trg_recovery_token_updated_at ON recovery_token")
    op.execute("DROP TRIGGER IF EXISTS trg_refresh_token_updated_at ON refresh_token")
    op.execute("""DROP TRIGGER IF EXISTS trg_user_updated_at ON "user" """)

    op.drop_table("recovery_token")
    op.drop_table("refresh_token")
    op.drop_table("user")
