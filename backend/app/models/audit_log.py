"""AuditLog ORM model — append-only audit trail (E-AUD).

Deliberately does NOT inherit BaseEntityMixin:
- No updated_at (implies mutability)
- No deleted_at (soft-delete is semantically wrong for an audit log)
Append-only is enforced at two layers: this model exposes no mutating methods,
and the migration adds PostgreSQL RULEs that silently block UPDATE and DELETE.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        # No FK: cascade actions (CASCADE/RESTRICT) on tenant deletion conflict with
        # the append-only RULEs. tenant_id is set from the validated CurrentUser.tenant_id.
        nullable=False,
        index=True,
    )
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        # No FK: RESTRICT on user deletion blocks test cleanup when audit rows exist.
        # actor_id is validated by the application (CurrentUser comes from verified JWT).
        nullable=False,
        index=True,
    )
    impersonado_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        # No FK: ON DELETE SET NULL would issue an UPDATE, blocked by the append-only RULE.
        nullable=True,
    )
    materia_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,  # no FK until C-06 creates materia table
    )
    accion: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    detalle: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    filas_afectadas: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
