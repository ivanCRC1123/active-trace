# Spec: fecha-academica

## Objetivo

Modelo ORM `FechaAcademica` (E15 del KB) y repositorio, que calendarizan instancias evaluativas (parciales, TPs, coloquios) por materia × cohorte × período dentro de un tenant.

## Enum `TipoEvaluacion` (`backend/app/models/base.py`)

```python
class TipoEvaluacion(str, enum.Enum):
    Parcial       = "Parcial"
    TP            = "TP"
    Coloquio      = "Coloquio"
    Recuperatorio = "Recuperatorio"
```

Se agrega junto a `EstadoBasico` en `base.py`. La migración 011 crea el Postgres ENUM `tipo_evaluacion` con `checkfirst=True`. C-14 usará `create_type=False` al referenciar el mismo type.

## Modelo ORM (`backend/app/models/fecha_academica.py`)

```python
class FechaAcademica(BaseEntityMixin):
    __tablename__ = "fecha_academica"

    materia_id : Mapped[UUID]           # FK → materia.id RESTRICT
    cohorte_id : Mapped[UUID]           # FK → cohorte.id RESTRICT
    tipo       : Mapped[TipoEvaluacion] # sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False)
    numero     : Mapped[int]            # Integer, nullable=False (1=primer, 2=segundo, etc.)
    periodo    : Mapped[str]            # String(20), nullable=False (ej: "2026-1", "2026-2")
    fecha      : Mapped[date]           # Date, nullable=False
    titulo     : Mapped[str]            # String(255), nullable=False

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "cohorte_id", "tipo", "numero", "periodo",
            name="uq_fecha_academica_instancia",
        ),
    )
```

**Hereda de `BaseEntityMixin`:** `id`, `tenant_id`, `created_at`, `updated_at`, `deleted_at`.

**`numero`:** entero positivo (≥ 1). El dominio habla de "1er parcial", "2do parcial", etc. No hay validación de máximo en el modelo (la lógica de cuántos parciales hay es configuración del tenant).

**`periodo`:** string libre (`"2026-1"`, `"2026-2"`, `"ANUAL-2026"`). No se normaliza en C-17; el tenant decide la nomenclatura.

## Repositorio (`backend/app/repositories/fecha_academica_repository.py`)

```python
class FechaAcademicaRepository(BaseRepository[FechaAcademica]):
    model_class = FechaAcademica

    async def get_by_instancia(
        self, materia_id: UUID, cohorte_id: UUID,
        tipo: TipoEvaluacion, numero: int, periodo: str,
    ) -> FechaAcademica | None:
        """Busca por unique key (tenant + materia + cohorte + tipo + numero + periodo)."""

    async def list_by_materia_cohorte(
        self, materia_id: UUID, cohorte_id: UUID, periodo: str | None = None,
    ) -> list[FechaAcademica]:
        """Lista fechas (no deleted), ordenadas por tipo y numero."""

    async def list_by_cohorte(
        self, cohorte_id: UUID, periodo: str | None = None,
    ) -> list[FechaAcademica]:
        """Vista de calendario: todas las fechas de la cohorte en el tenant."""
```

## Schemas Pydantic (`backend/app/schemas/programas_y_fechas.py`)

```python
class FechaAcademicaCreate(BaseModel):
    materia_id : UUID
    cohorte_id : UUID
    tipo       : TipoEvaluacion
    numero     : int            # ge=1
    periodo    : str            # min_length=1, max_length=20
    fecha      : date
    titulo     : str            # min_length=1, max_length=255

class FechaAcademicaUpdate(BaseModel):
    fecha  : date | None = None
    titulo : str | None = None

class FechaAcademicaResponse(BaseModel):
    id         : UUID
    tenant_id  : UUID
    materia_id : UUID
    cohorte_id : UUID
    tipo       : TipoEvaluacion
    numero     : int
    periodo    : str
    fecha      : date
    titulo     : str
    created_at : datetime
    updated_at : datetime

    model_config = ConfigDict(extra='forbid', from_attributes=True)
```

**Nota:** `FechaAcademicaUpdate` expone solo `fecha` y `titulo`. La combinación `(materia_id, cohorte_id, tipo, numero, periodo)` es inmutable; para cambiarla se elimina y recrea.

## Lógica de fragmento LMS (`ProgramasService.generar_fragmento_lms`)

Dado `materia_id + cohorte_id + periodo (opcional)`:

1. Recupera todas las `FechaAcademica` del tenant que cumplan los filtros (no deleted), ordenadas por `tipo` y `numero`.
2. Agrupa por `tipo` (Parcial, TP, Coloquio, Recuperatorio).
3. Genera Markdown:

```markdown
## Fechas académicas — {materia.nombre} | Cohorte {cohorte.nombre}

### Parciales
- **1er Parcial** — 15 de marzo de 2026
- **2do Parcial** — 12 de mayo de 2026

### Trabajos Prácticos
- **TP 1** — 30 de marzo de 2026

### Coloquios
- **Coloquio Final** — 20 de junio de 2026
```

4. Si no hay fechas, devuelve `{"fragmento": ""}` (no error).
5. La resolución del nombre de materia y cohorte requiere un join o dos queries extra; se resuelven en el servicio (no en el router).

## Criterios de aceptación

- [ ] `fecha_academica` en DB con columnas y constraints según spec.
- [ ] `tipo_evaluacion` Postgres ENUM creado con `checkfirst=True` en migración.
- [ ] `unique constraint` impide duplicar instancia evaluativa en el mismo tenant.
- [ ] `list_by_materia_cohorte` ordena por tipo (orden canónico: Parcial, TP, Coloquio, Recuperatorio) y `numero` ASC.
- [ ] `generar_fragmento_lms` devuelve Markdown válido con las fechas formateadas en español.
- [ ] Fragmento vacío (`""`) si no hay fechas que cumplan los criterios (no 404).
- [ ] `FechaAcademicaUpdate` con `extra='forbid'` rechaza campos no declarados.
- [ ] `numero` rechaza valores < 1 en el schema (Pydantic `ge=1`).
