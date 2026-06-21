"""ComentarioTarea — hilo de comentarios sobre una Tarea (E12, C-16).

Los comentarios son inmutables una vez creados: no tienen updated_at.
Se puede soft-delete pero no editar.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TenantScopedMixin, TimeStampedMixin


class ComentarioTarea(Base, TimeStampedMixin, SoftDeleteMixin, TenantScopedMixin):
    __tablename__ = "comentario_tarea"

    tarea_id: Mapped[UUID] = mapped_column(
        ForeignKey("tarea.id", ondelete="RESTRICT"), nullable=False
    )
    autor_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_comentario_tarea_tarea_id", "tarea_id"),
        Index("ix_comentario_tarea_tenant_id", "tenant_id"),
    )
