# Spec: Calificacion (E7) y UmbralMateria (E8)

## Calificacion — Modelo SQLAlchemy

Archivo: `backend/app/models/calificacion.py`

```python
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class OrigenCalificacion(str, enum.Enum):
    Importado = "Importado"
    Manual = "Manual"


class Calificacion(Base, BaseEntityMixin):
    __tablename__ = "calificacion"

    entrada_padron_id: Mapped[UUID] = mapped_column(
        ForeignKey("entrada_padron.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    asignacion_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=True
    )
    actividad: Mapped[str] = mapped_column(String(500), nullable=False)
    nota_numerica: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    nota_textual: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    aprobado: Mapped[bool] = mapped_column(nullable=False)
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="Importado")
    importado_at: Mapped[datetime] = mapped_column(
        server_default=sa.func.now(), nullable=False
    )
```

## UmbralMateria — Modelo SQLAlchemy

Archivo: `backend/app/models/umbral_materia.py`

```python
from __future__ import annotations

from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin

DEFAULT_VALORES_APROBATORIOS = ["Satisfactorio", "Supera lo esperado"]


class UmbralMateria(Base, BaseEntityMixin):
    __tablename__ = "umbral_materia"

    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    umbral_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    valores_aprobatorios: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        server_default=sa.text("'[\"Satisfactorio\", \"Supera lo esperado\"]'::json"),
        default=list,
    )
```

## Reglas de invariante

1. `(nota_numerica IS NULL AND nota_textual IS NULL)` debe ser evitado — al menos uno debe tener valor.
2. `aprobado` no puede ser NULL. Siempre se calcula antes de persistir.
3. `(entrada_padron_id, actividad, asignacion_id)` es único cuando `deleted_at IS NULL`
   (índice único en migración). Permite re-importar: si ya existe la combinación, se hace
   upsert (update del registro existente con la nueva nota).
4. `asignacion_id` debe pertenecer al mismo `tenant_id` que `Calificacion`. Validar en servicio.

## UmbralMateria invariantes

1. `umbral_pct` entre 1 y 100 (validado en schema Pydantic con `ge=1, le=100`).
2. `valores_aprobatorios` lista no-vacía si existe registro.
3. `(asignacion_id, materia_id)` único cuando `deleted_at IS NULL`.
4. La modificación del umbral NO recalcula calificaciones existentes (D-C10-2).
