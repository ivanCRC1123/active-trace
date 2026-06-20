"""Evaluacion models — E14 (convocatoria, convocados, reserva, resultado).

Four ORM classes for the formal evaluation workflow (Épica 7 / FL-07):

- Evaluacion:          convocatoria with cupo_total (0 = unlimited).
- ConvocadoEvaluacion: imported list of eligible students (PII: email_cifrado + email_hash).
- ReservaEvaluacion:   student slot reservation (Activa → Cancelada).
- ResultadoEvaluacion: final grade per student (updatable with audit log).

TipoEvaluacion is reused from app.models.base (created in migration 011, create_type=False).
EstadoReserva is new, created in migration 012.
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EncryptedString, TipoEvaluacion


class EstadoReserva(str, enum.Enum):
    Activa = "Activa"
    Cancelada = "Cancelada"


class Evaluacion(Base, BaseEntityMixin):
    __tablename__ = "evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "cohorte_id", "tipo", "instancia",
            name="uq_evaluacion_instancia",
        ),
    )

    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cohorte_id: Mapped[UUID] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[TipoEvaluacion] = mapped_column(
        sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False),
        nullable=False,
    )
    instancia: Mapped[str] = mapped_column(String(255), nullable=False)
    dias_disponibles: Mapped[int] = mapped_column(Integer, nullable=False)
    cupo_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<Evaluacion id={self.id} tipo={self.tipo} instancia={self.instancia!r}>"


class ConvocadoEvaluacion(Base, BaseEntityMixin):
    """Alumno importado a una convocatoria de evaluación.

    PII: email_cifrado (AES-256-GCM via EncryptedString) + email_hash (HMAC-SHA256 blind index).
    nombre/apellidos in plaintext (same pattern as EntradaPadron §E6).
    """

    __tablename__ = "convocado_evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "evaluacion_id", "usuario_id",
            name="uq_convocado_evaluacion_usuario",
        ),
        Index("idx_convocado_email_hash", "tenant_id", "evaluacion_id", "email_hash"),
    )

    evaluacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluacion.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(255), nullable=False)
    email_cifrado: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:
        return f"<ConvocadoEvaluacion id={self.id} evaluacion_id={self.evaluacion_id}>"


class ReservaEvaluacion(Base, BaseEntityMixin):
    __tablename__ = "reserva_evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "evaluacion_id", "alumno_id",
            name="uq_reserva_evaluacion_alumno",
        ),
    )

    evaluacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluacion.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    alumno_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fecha_hora: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    estado: Mapped[EstadoReserva] = mapped_column(
        sa.Enum(EstadoReserva, name="estado_reserva", create_type=True),
        nullable=False,
        default=EstadoReserva.Activa,
    )

    def __repr__(self) -> str:
        return f"<ReservaEvaluacion id={self.id} alumno_id={self.alumno_id} estado={self.estado}>"


class ResultadoEvaluacion(Base, BaseEntityMixin):
    __tablename__ = "resultado_evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "evaluacion_id", "alumno_id",
            name="uq_resultado_evaluacion_alumno",
        ),
    )

    evaluacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluacion.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    alumno_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nota_final: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<ResultadoEvaluacion id={self.id} alumno_id={self.alumno_id} nota={self.nota_final!r}>"
