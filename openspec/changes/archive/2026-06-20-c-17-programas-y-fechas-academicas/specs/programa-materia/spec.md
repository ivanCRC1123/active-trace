# Spec: programa-materia

## Objetivo

Modelo ORM `ProgramaMateria` (E16 del KB) y repositorio correspondiente, que persisten la referencia al documento oficial de un programa de materia para una combinación de materia × carrera × cohorte dentro de un tenant.

## Modelo ORM (`backend/app/models/programa_materia.py`)

```python
class ProgramaMateria(BaseEntityMixin):
    __tablename__ = "programa_materia"

    materia_id         : Mapped[UUID]  # FK → materia.id RESTRICT
    carrera_id         : Mapped[UUID]  # FK → carrera.id RESTRICT
    cohorte_id         : Mapped[UUID]  # FK → cohorte.id RESTRICT
    titulo             : Mapped[str]   # String(255), nullable=False
    referencia_archivo : Mapped[str]   # Text, nullable=False (opaque reference)
    cargado_at         : Mapped[datetime]  # DateTime(timezone=True), server_default=now()

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "carrera_id", "cohorte_id",
            name="uq_programa_materia_tenant_materia_carrera_cohorte",
        ),
    )
```

**Hereda de `BaseEntityMixin`:** `id` (UUID PK), `tenant_id` (UUID FK→tenant RESTRICT), `created_at`, `updated_at`, `deleted_at`.

**FKs:** todas con `ondelete="RESTRICT"` (el soft-delete es la operación normal; la DB protege contra borrados físicos accidentales).

**`referencia_archivo`:** campo opaco de tipo `Text`. El sistema no valida ni interpreta su contenido. Puede ser una URL, una key de S3, un UUID, etc.

**`cargado_at`:** timestamp con zona horaria; se auto-setea en la creación y no es modificable por el cliente.

## Repositorio (`backend/app/repositories/programa_materia_repository.py`)

```python
class ProgramaMateriaRepository(BaseRepository[ProgramaMateria]):
    model_class = ProgramaMateria

    async def get_by_combinacion(
        self, materia_id: UUID, carrera_id: UUID, cohorte_id: UUID
    ) -> ProgramaMateria | None:
        """Busca por (tenant_id, materia_id, carrera_id, cohorte_id) sin deleted."""

    async def list_by_materia(self, materia_id: UUID) -> list[ProgramaMateria]:
        """Lista todos (no deleted) filtrando por materia_id dentro del tenant."""

    async def list_by_cohorte(self, cohorte_id: UUID) -> list[ProgramaMateria]:
        """Lista todos (no deleted) filtrando por cohorte_id dentro del tenant."""
```

`BaseRepository.get_by_id`, `create`, `update`, `soft_delete` cubren el CRUD base con tenant-scope automático.

## Schemas Pydantic (`backend/app/schemas/programas_y_fechas.py`)

Todos con `model_config = ConfigDict(extra='forbid')`.

```python
class ProgramaMateriaCreate(BaseModel):
    materia_id         : UUID
    carrera_id         : UUID
    cohorte_id         : UUID
    titulo             : str   # min_length=1, max_length=255
    referencia_archivo : str   # min_length=1

class ProgramaMateriaUpdate(BaseModel):
    titulo             : str | None = None
    referencia_archivo : str | None = None

class ProgramaMateriaResponse(BaseModel):
    id                 : UUID
    tenant_id          : UUID
    materia_id         : UUID
    carrera_id         : UUID
    cohorte_id         : UUID
    titulo             : str
    referencia_archivo : str
    cargado_at         : datetime
    created_at         : datetime
    updated_at         : datetime

    model_config = ConfigDict(extra='forbid', from_attributes=True)
```

**Nota:** `ProgramaMateriaUpdate` no expone `materia_id`, `carrera_id` ni `cohorte_id` — la combinación es inmutable. Para cambiarla, se elimina (soft) y se crea de nuevo.

## Criterios de aceptación

- [ ] `programa_materia` en DB con columnas y constraints según spec.
- [ ] `BaseRepository.tenant_id` filtra automáticamente; ninguna query cruza tenants.
- [ ] `get_by_combinacion` devuelve `None` si la fila tiene `deleted_at IS NOT NULL`.
- [ ] FK a `materia`, `carrera` y `cohorte` con `RESTRICT` (no cascade).
- [ ] `referencia_archivo` almacenada sin transformación (opaque).
- [ ] `cargado_at` se setea en `INSERT`, no es actualizable vía PATCH.
- [ ] `ProgramaMateriaUpdate` con `extra='forbid'` rechaza campos no declarados (400).
