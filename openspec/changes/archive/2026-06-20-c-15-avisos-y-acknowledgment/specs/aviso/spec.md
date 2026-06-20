# Spec — Aviso (modelo + endpoints de gestión)

## Modelo ORM (`backend/app/models/aviso.py`)

```python
import enum
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, BaseEntityMixin
from uuid import UUID

class AlcanceAviso(str, enum.Enum):
    Global     = "Global"
    PorMateria = "PorMateria"
    PorCohorte = "PorCohorte"
    PorRol     = "PorRol"

class SeveridadAviso(str, enum.Enum):
    Info        = "Info"
    Advertencia = "Advertencia"
    Critico     = "Critico"

class Aviso(Base, BaseEntityMixin):
    __tablename__ = "aviso"

    alcance:     Mapped[AlcanceAviso]    # Enum, create_type=True
    materia_id:  Mapped[UUID | None]    # FK → materia.id RESTRICT, nullable
    cohorte_id:  Mapped[UUID | None]    # FK → cohorte.id RESTRICT, nullable
    rol_destino: Mapped[str | None]     # String(50), nullable — "ALUMNO"|"TUTOR"|...
    severidad:   Mapped[SeveridadAviso] # Enum, create_type=True
    titulo:      Mapped[str]            # String(255)
    cuerpo:      Mapped[str]            # Text
    inicio_en:   Mapped[datetime]       # DateTime(timezone=True)
    fin_en:      Mapped[datetime]       # DateTime(timezone=True)
    orden:       Mapped[int]            # Integer, default=0
    activo:      Mapped[bool]           # Boolean, default=True
    requiere_ack: Mapped[bool]          # Boolean, default=False

    __table_args__ = (
        sa.Index("idx_aviso_tenant", "tenant_id"),
        sa.Index("idx_aviso_vigencia", "tenant_id", "activo", "inicio_en", "fin_en"),
        sa.Index("idx_aviso_alcance", "tenant_id", "alcance"),
    )
```

## Schemas Pydantic (`backend/app/schemas/avisos.py`)

Todos con `model_config = ConfigDict(extra='forbid')`.

**`AvisoCreate`**:
```python
alcance:      AlcanceAviso
materia_id:   UUID | None = None
cohorte_id:   UUID | None = None
rol_destino:  Literal["ALUMNO","TUTOR","PROFESOR","COORDINADOR","NEXO","ADMIN","FINANZAS"] | None = None
severidad:    SeveridadAviso
titulo:       str  # min_length=1, max_length=255
cuerpo:       str  # min_length=1
inicio_en:    datetime
fin_en:       datetime
orden:        int = 0  # ge=0
activo:       bool = True
requiere_ack: bool = False
```

**`AvisoUpdate`** (todos opcionales):
```python
titulo:       str | None = None  # max_length=255
cuerpo:       str | None = None
inicio_en:    datetime | None = None
fin_en:       datetime | None = None
orden:        int | None = None   # ge=0
activo:       bool | None = None
requiere_ack: bool | None = None
# alcance, materia_id, cohorte_id, rol_destino: NO modificables post-creación
# (cambiar el alcance de un aviso publicado es un efecto colateral confuso)
```

**`AvisoResponse`** (`from_attributes=True`):
```python
id, tenant_id, alcance, materia_id, cohorte_id, rol_destino, severidad
titulo, cuerpo, inicio_en, fin_en, orden, activo, requiere_ack
created_at, updated_at
```

**`AvisoStats`**:
```python
aviso_id:       UUID
confirmaciones: int
```

## Repositorio (`AvisoRepository`)

```python
class AvisoRepository(BaseRepository[Aviso]):
    model_class = Aviso

    async def list_all(self) -> list[Aviso]:
        # Admin view: todos (activos e inactivos), sin filtro de vigencia, deleted_at IS NULL
        # ORDER BY orden ASC, inicio_en DESC

    async def list_visibles_para_usuario(
        self,
        *,
        roles: set[str],
        materias: set[UUID],
        cohortes: set[UUID],
        usuario_id: UUID,
        now: datetime,
    ) -> list[Aviso]:
        # Ver design.md §D4 para el OR compuesto + ack exclusion

    async def count_confirmaciones(self, aviso_id: UUID) -> int:
        # SELECT COUNT(*) FROM acknowledgment_aviso WHERE aviso_id=:id AND deleted_at IS NULL
```

## Endpoints de gestión (`avisos:publicar`)

| Método | Ruta | Status | Descripción |
|--------|------|--------|-------------|
| `GET`  | `/api/v1/avisos` | 200 | Listado admin (todos, sin filtro de vigencia) |
| `POST` | `/api/v1/avisos` | 201 | Crear aviso; valida reglas de scope + `fin_en > inicio_en` |
| `GET`  | `/api/v1/avisos/{id}` | 200/404 | Detalle de aviso |
| `PATCH` | `/api/v1/avisos/{id}` | 200/404 | Editar campos mutables (no alcance ni context IDs) |
| `DELETE` | `/api/v1/avisos/{id}` | 204/404 | Soft delete |
| `GET`  | `/api/v1/avisos/{id}/stats` | 200/404 | `{ aviso_id, confirmaciones }` |

### Mapeo ValueError → HTTPException

| ValueError message | Status | Detail |
|--------------------|--------|--------|
| `"not found"` | 404 | aviso no existe o es de otro tenant |
| `"materia not found"` | 404 | materia_id no pertenece al tenant |
| `"cohorte not found"` | 404 | cohorte_id no pertenece al tenant |
| `"fin_en_before_inicio"` | 422 | fin_en <= inicio_en |
| `"scope_context_missing"` | 422 | alcance requiere campo no proporcionado |

### Validaciones de scope en `create_aviso`

```
alcance=Global      → materia_id=None, cohorte_id=None, rol_destino=None   (o ValueError)
alcance=PorMateria  → materia_id required, cohorte_id=None, rol_destino=None
alcance=PorCohorte  → cohorte_id required, materia_id=None, rol_destino=None
alcance=PorRol      → rol_destino required, materia_id=None, cohorte_id=None
```

`fin_en > inicio_en` siempre (ValueError "fin_en_before_inicio" si no).
