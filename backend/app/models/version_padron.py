"""VersionPadron model — padrón header (E6).

One active version per (tenant_id, materia_id, cohorte_id) at a time.
Enforced by partial unique index `uq_version_padron_activa` (migration 007).
"""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class VersionPadron(Base, BaseEntityMixin):
    __tablename__ = "version_padron"

    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    cohorte_id: Mapped[UUID] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=False
    )
    cargado_por: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    cargado_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<VersionPadron id={self.id} materia_id={self.materia_id} activa={self.activa}>"
