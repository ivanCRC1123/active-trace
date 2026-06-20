"""005_carrera_cohorte_materia

Create carrera, cohorte and materia tables for the academic catalog (E1-E3).
Introduces the shared `estado_basico` PostgreSQL ENUM type (Activa/Inactiva).

Revision ID: b5c6d7e8f9a0
Revises: c05af7b8d9e1
Create Date: 2026-06-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "c05af7b8d9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# BaseEntityMixin column template for reuse.
_MIXIN_COLS = [
    sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
    sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
]


def upgrade() -> None:
    """Create estado_basico ENUM, then carrera/cohorte/materia tables."""

    # 1. Create the shared PostgreSQL ENUM type used by all 3 tables.
    op.execute("CREATE TYPE estado_basico AS ENUM ('Activa', 'Inactiva')")

    # 2. carrera table
    op.create_table(
        "carrera",
        *_MIXIN_COLS,
        sa.Column("codigo", sa.VARCHAR(length=50), nullable=False),
        sa.Column("nombre", sa.VARCHAR(length=255), nullable=False),
        sa.Column(
            "estado",
            postgresql.ENUM("Activa", "Inactiva", name="estado_basico", create_type=False),
            nullable=False,
            server_default="Activa",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("carrera_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"],
            name=op.f("carrera_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "codigo", name=op.f("uq_carrera_tenant_codigo")),
    )
    op.create_index("idx_carrera_tenant", "carrera", ["tenant_id"])
    op.create_index("idx_carrera_codigo", "carrera", ["codigo"])
    op.create_index("idx_carrera_estado", "carrera", ["estado"])
    op.execute(
        """
        CREATE TRIGGER trg_carrera_updated_at
        BEFORE UPDATE ON carrera
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # 3. cohorte table
    op.create_table(
        "cohorte",
        *_MIXIN_COLS,
        sa.Column("carrera_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.VARCHAR(length=100), nullable=False),
        sa.Column("anio", sa.INTEGER(), nullable=False),
        sa.Column("vig_desde", sa.DATE(), nullable=False),
        sa.Column("vig_hasta", sa.DATE(), nullable=True),
        sa.Column(
            "estado",
            postgresql.ENUM("Activa", "Inactiva", name="estado_basico", create_type=False),
            nullable=False,
            server_default="Activa",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("cohorte_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"],
            name=op.f("cohorte_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["carrera_id"], ["carrera.id"],
            name=op.f("cohorte_carrera_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "carrera_id", "nombre",
            name=op.f("uq_cohorte_tenant_carrera_nombre"),
        ),
    )
    op.create_index("idx_cohorte_tenant", "cohorte", ["tenant_id"])
    op.create_index("idx_cohorte_carrera", "cohorte", ["carrera_id"])
    op.create_index("idx_cohorte_estado", "cohorte", ["estado"])
    op.execute(
        """
        CREATE TRIGGER trg_cohorte_updated_at
        BEFORE UPDATE ON cohorte
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )

    # 4. materia table
    op.create_table(
        "materia",
        *_MIXIN_COLS,
        sa.Column("codigo", sa.VARCHAR(length=50), nullable=False),
        sa.Column("nombre", sa.VARCHAR(length=255), nullable=False),
        sa.Column(
            "estado",
            postgresql.ENUM("Activa", "Inactiva", name="estado_basico", create_type=False),
            nullable=False,
            server_default="Activa",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("materia_pkey")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"],
            name=op.f("materia_tenant_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "codigo", name=op.f("uq_materia_tenant_codigo")),
    )
    op.create_index("idx_materia_tenant", "materia", ["tenant_id"])
    op.create_index("idx_materia_codigo", "materia", ["codigo"])
    op.create_index("idx_materia_estado", "materia", ["estado"])
    op.execute(
        """
        CREATE TRIGGER trg_materia_updated_at
        BEFORE UPDATE ON materia
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
        """
    )


def downgrade() -> None:
    """Drop materia, cohorte, carrera tables and estado_basico ENUM."""

    op.execute("DROP TRIGGER IF EXISTS trg_materia_updated_at ON materia")
    op.execute("DROP TRIGGER IF EXISTS trg_cohorte_updated_at ON cohorte")
    op.execute("DROP TRIGGER IF EXISTS trg_carrera_updated_at ON carrera")

    op.drop_index("idx_materia_estado", table_name="materia")
    op.drop_index("idx_materia_codigo", table_name="materia")
    op.drop_index("idx_materia_tenant", table_name="materia")
    op.drop_table("materia")

    op.drop_index("idx_cohorte_estado", table_name="cohorte")
    op.drop_index("idx_cohorte_carrera", table_name="cohorte")
    op.drop_index("idx_cohorte_tenant", table_name="cohorte")
    op.drop_table("cohorte")

    op.drop_index("idx_carrera_estado", table_name="carrera")
    op.drop_index("idx_carrera_codigo", table_name="carrera")
    op.drop_index("idx_carrera_tenant", table_name="carrera")
    op.drop_table("carrera")

    # Drop shared ENUM type after all tables using it are gone.
    op.execute("DROP TYPE IF EXISTS estado_basico")
