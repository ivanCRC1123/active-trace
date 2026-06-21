"""015_perfil_sexo — agrega campo sexo nullable a tabla user (C-20 perfil).

Revision ID: a5b6c7d8e9f0
Revises: f6a7b8c9d0e1
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a5b6c7d8e9f0"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("sexo", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "sexo")
