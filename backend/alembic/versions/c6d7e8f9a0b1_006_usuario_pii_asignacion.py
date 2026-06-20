"""006: usuario PII cifrada + tabla asignacion.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-20
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


# ── Crypto inlineado para backfill (no importar desde app) ────────────────────


def _key_from_env() -> str:
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY not set — no se puede hacer el backfill de email")
    return key


def _inline_encrypt(plaintext: str, key_str: str) -> str:
    """AES-256-GCM encrypt — inlineado para no depender de imports de app."""
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = key_str.encode("utf-8")
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def _inline_hmac(email: str, key_str: str) -> str:
    """HMAC-SHA256 del email normalizado — inlineado para no depender de imports de app."""
    import hashlib
    import hmac as _hmac

    return _hmac.new(
        key_str.encode("utf-8"),
        email.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ── Upgrade ───────────────────────────────────────────────────────────────────


def upgrade() -> None:
    enc_key = _key_from_env()

    # ── 1. Renombrar apellido → apellidos ────────────────────────────────────
    op.alter_column("user", "apellido", new_column_name="apellidos")

    # ── 2. Agregar email_cifrado + email_hash como nullable (para backfill) ──
    op.add_column("user", sa.Column("email_cifrado", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("email_hash", sa.String(64), nullable=True))

    # ── 3. Backfill filas existentes ─────────────────────────────────────────
    bind = op.get_bind()
    rows = bind.execute(
        sa.text('SELECT id, email FROM "user" WHERE email IS NOT NULL')
    ).fetchall()
    for uid, email in rows:
        ec = _inline_encrypt(email, enc_key)
        eh = _inline_hmac(email, enc_key)
        bind.execute(
            sa.text(
                'UPDATE "user" SET email_cifrado = :ec, email_hash = :eh WHERE id = :id'
            ),
            {"ec": ec, "eh": eh, "id": str(uid)},
        )

    # ── 4. Hacer NOT NULL los campos de email ────────────────────────────────
    op.alter_column("user", "email_cifrado", nullable=False)
    op.alter_column("user", "email_hash", nullable=False)

    # ── 5. Eliminar columna email plaintext ──────────────────────────────────
    # El nombre del constraint UNIQUE lo genera PostgreSQL como "user_email_key"
    op.drop_constraint("user_email_key", "user", type_="unique")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_column("user", "email")

    # ── 6. Unicidad + índice sobre email_hash (por tenant) ───────────────────
    op.create_unique_constraint(
        "uq_user_tenant_email_hash", "user", ["tenant_id", "email_hash"]
    )
    op.create_index("idx_user_email_hash", "user", ["email_hash"])

    # ── 7. Campos PII adicionales (todos nullable) ───────────────────────────
    op.add_column("user", sa.Column("dni_cifrado", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("cuil_cifrado", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("cbu_cifrado", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("alias_cbu_cifrado", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("banco", sa.String(255), nullable=True))
    op.add_column("user", sa.Column("regional", sa.String(255), nullable=True))
    op.add_column("user", sa.Column("legajo", sa.String(100), nullable=True))
    op.add_column("user", sa.Column("legajo_profesional", sa.String(100), nullable=True))
    op.add_column(
        "user",
        sa.Column(
            "facturador",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ── 8. Tabla asignacion ───────────────────────────────────────────────────
    op.create_table(
        "asignacion",
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
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rol_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rol.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "materia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materia.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "carrera_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("carrera.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "cohorte_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cohorte.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "comisiones",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "responsable_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date(), nullable=True),
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

    # Trigger updated_at en asignacion
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_asignacion_updated_at
            BEFORE UPDATE ON asignacion
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
            """
        )
    )

    # Indexes parciales (WHERE deleted_at IS NULL)
    op.create_index(
        "idx_asignacion_tenant",
        "asignacion",
        ["tenant_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_asignacion_usuario",
        "asignacion",
        ["usuario_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_asignacion_rol",
        "asignacion",
        ["rol_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_asignacion_materia",
        "asignacion",
        ["materia_id"],
        postgresql_where=sa.text("deleted_at IS NULL AND materia_id IS NOT NULL"),
    )
    op.create_index(
        "idx_asignacion_cohorte",
        "asignacion",
        ["cohorte_id"],
        postgresql_where=sa.text("deleted_at IS NULL AND cohorte_id IS NOT NULL"),
    )
    op.create_index(
        "idx_asignacion_vigencia",
        "asignacion",
        ["tenant_id", "desde", "hasta"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


# ── Downgrade ─────────────────────────────────────────────────────────────────


def downgrade() -> None:
    # Eliminar tabla asignacion y sus índices
    op.drop_index("idx_asignacion_vigencia", table_name="asignacion")
    op.drop_index("idx_asignacion_cohorte", table_name="asignacion")
    op.drop_index("idx_asignacion_materia", table_name="asignacion")
    op.drop_index("idx_asignacion_rol", table_name="asignacion")
    op.drop_index("idx_asignacion_usuario", table_name="asignacion")
    op.drop_index("idx_asignacion_tenant", table_name="asignacion")
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_asignacion_updated_at ON asignacion"))
    op.drop_table("asignacion")

    # Eliminar campos de perfil + PII de user
    op.drop_column("user", "facturador")
    op.drop_column("user", "legajo_profesional")
    op.drop_column("user", "legajo")
    op.drop_column("user", "regional")
    op.drop_column("user", "banco")
    op.drop_column("user", "alias_cbu_cifrado")
    op.drop_column("user", "cbu_cifrado")
    op.drop_column("user", "cuil_cifrado")
    op.drop_column("user", "dni_cifrado")

    # Restaurar email plaintext
    op.drop_index("idx_user_email_hash", table_name="user")
    op.drop_constraint("uq_user_tenant_email_hash", "user", type_="unique")
    op.drop_column("user", "email_hash")
    op.drop_column("user", "email_cifrado")

    op.add_column(
        "user",
        sa.Column("email", sa.String(255), nullable=True),
    )
    op.create_unique_constraint("user_email_key", "user", ["email"])
    op.create_index("ix_user_email", "user", ["email"])

    # Renombrar apellidos → apellido
    op.alter_column("user", "apellidos", new_column_name="apellido")
