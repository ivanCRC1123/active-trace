# Spec: evaluacion

## Objetivo

Modelos ORM `Evaluacion` y `ConvocadoEvaluacion`, y su repositorio. Representan la convocatoria
de evaluación formal (E14 del KB, extendido con `cupo_total` y `ConvocadoEvaluacion`).

## Enum `EstadoReserva` (`backend/app/models/evaluacion.py`)

```python
class EstadoReserva(str, enum.Enum):
    Activa    = "Activa"
    Cancelada = "Cancelada"
```

Enum Postgres `estado_reserva`, creado en migración 012 con `checkfirst=True`.
Se define en `evaluacion.py` (junto a los modelos) para mantener cohesión. No va en `base.py`
porque es exclusivo de este módulo.

## Modelo `Evaluacion` (`backend/app/models/evaluacion.py`)

```python
class Evaluacion(Base, BaseEntityMixin):
    __tablename__ = "evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "cohorte_id", "tipo", "instancia",
            name="uq_evaluacion_instancia",
        ),
    )

    materia_id       : Mapped[UUID]            # FK → materia.id RESTRICT, index=True
    cohorte_id       : Mapped[UUID]            # FK → cohorte.id RESTRICT, index=True
    tipo             : Mapped[TipoEvaluacion]  # sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False)
    instancia        : Mapped[str]             # String(255), ej: "Coloquio Final"
    dias_disponibles : Mapped[int]             # Integer, ≥ 1 — ventana de inscripción en días
    cupo_total       : Mapped[int]             # Integer, ≥ 0 — 0 = sin límite (D2)
```

**Hereda de `BaseEntityMixin`:** `id`, `tenant_id`, `created_at`, `updated_at`, `deleted_at`.

**`tipo`:** importa `TipoEvaluacion` desde `app.models.base`; usa `create_type=False` porque
el Postgres ENUM ya existe desde la migración 011 de C-17.

**Unique constraint:** `(tenant_id, materia_id, cohorte_id, tipo, instancia)` — una sola
convocatoria activa con ese nombre para esa materia × cohorte. Si se necesita un segundo turno
con el mismo nombre, se hace soft-delete y recreación.

## Modelo `ConvocadoEvaluacion` (`backend/app/models/evaluacion.py`)

Mismo patrón PII que `EntradaPadron` (C-09): email guardado con `EncryptedString`
TypeDecorator (AES-256-GCM) + `email_hash` (HMAC-SHA256) como blind index para lookups.
`nombre` y `apellidos` se almacenan en plaintext (igual que en E6).

```python
class ConvocadoEvaluacion(Base, BaseEntityMixin):
    __tablename__ = "convocado_evaluacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "evaluacion_id", "usuario_id",
            name="uq_convocado_evaluacion_usuario",
        ),
        Index("idx_convocado_email_hash", "tenant_id", "evaluacion_id", "email_hash"),
    )

    evaluacion_id : Mapped[UUID]        # FK → evaluacion.id RESTRICT, index=True
    usuario_id    : Mapped[UUID | None] # FK → user.id RESTRICT, nullable=True
    nombre        : Mapped[str]         # String(255), plaintext (como EntradaPadron)
    apellidos     : Mapped[str]         # String(255), plaintext
    email_cifrado : Mapped[str]         # EncryptedString (AES-256-GCM), nunca en logs
    email_hash    : Mapped[str]         # String(64), HMAC-SHA256 blind index
```

**`email_cifrado`**: TypeDecorator `EncryptedString` de `app.models.base` — cifra en escritura,
descifra en lectura automáticamente. El servicio trabaja con plaintext; nunca se loguea.

**`email_hash`**: `hmac_email(email)` de `app.core.encryption` — determinístico, permite lookup
por email sin exponer el plaintext. Se usa para deduplicación en `bulk_create` cuando
`usuario_id IS NULL`.

**`usuario_id` nullable**: un alumno puede ser convocado antes de tener cuenta. La reserva,
en cambio, requiere `alumno_id` (usuario autenticado).

**Unique constraint**: sobre `(tenant_id, evaluacion_id, usuario_id)` cuando usuario_id no es
null. Para alumnos sin cuenta, la deduplicación en `bulk_create` usa `email_hash`.

## Repositorio (`backend/app/repositories/evaluacion_repository.py`)

```python
class EvaluacionRepository(BaseRepository[Evaluacion]):
    model_class = Evaluacion

    async def get_by_instancia(
        self, materia_id: UUID, cohorte_id: UUID,
        tipo: TipoEvaluacion, instancia: str,
    ) -> Evaluacion | None:
        """Busca por unique key (tenant + materia + cohorte + tipo + instancia)."""

    async def list_by_materia_cohorte(
        self, materia_id: UUID, cohorte_id: UUID,
    ) -> list[Evaluacion]:
        """Lista convocatorias no eliminadas, ordenadas por tipo y created_at ASC."""

    async def count_reservas_activas(self, evaluacion_id: UUID) -> int:
        """Cuenta ReservaEvaluacion activas para calcular cupos libres."""
        # SELECT COUNT(*) FROM reserva_evaluacion
        # WHERE evaluacion_id = ? AND estado = 'Activa' AND deleted_at IS NULL AND tenant_id = ?

    async def count_convocados(self, evaluacion_id: UUID) -> int:
        """Cuenta ConvocadoEvaluacion no eliminados."""

    async def count_resultados(self, evaluacion_id: UUID) -> int:
        """Cuenta ResultadoEvaluacion no eliminados."""


class ConvocadoRepository(BaseRepository[ConvocadoEvaluacion]):
    model_class = ConvocadoEvaluacion

    async def list_by_evaluacion(self, evaluacion_id: UUID) -> list[ConvocadoEvaluacion]:
        """Lista convocados de una evaluacion, no eliminados."""

    async def bulk_create(
        self, tenant_id: UUID, evaluacion_id: UUID,
        filas: list[dict],
    ) -> int:
        """Inserta lote de convocados; devuelve cantidad insertada. Idempotente:
        - Si usuario_id no es None: omite filas con ese usuario_id ya existente.
        - Si usuario_id es None: omite filas cuyo email_hash ya existe en la misma evaluacion.
        """

    async def get_by_email_hash(
        self, evaluacion_id: UUID, email_hash: str,
    ) -> ConvocadoEvaluacion | None:
        """Lookup por blind index para deduplicación de alumnos sin cuenta."""
```

## Schemas Pydantic (`backend/app/schemas/coloquios.py`)

```python
class EvaluacionCreate(BaseModel):
    materia_id       : UUID
    cohorte_id       : UUID
    tipo             : TipoEvaluacion
    instancia        : str              # min_length=1, max_length=255
    dias_disponibles : int              # ge=1
    cupo_total       : int              # ge=0 (0 = sin límite)

class EvaluacionUpdate(BaseModel):
    instancia        : str | None = None
    dias_disponibles : int | None = None  # ge=1 si se provee
    cupo_total       : int | None = None  # ge=0 si se provee

class EvaluacionResponse(BaseModel):
    id               : UUID
    tenant_id        : UUID
    materia_id       : UUID
    cohorte_id       : UUID
    tipo             : TipoEvaluacion
    instancia        : str
    dias_disponibles : int
    cupo_total       : int
    created_at       : datetime
    updated_at       : datetime
    model_config = ConfigDict(extra='forbid', from_attributes=True)

class MetricasConvocatoria(BaseModel):
    evaluacion_id   : UUID
    convocados      : int
    reservas_activas: int
    cupos_libres    : int  # cupo_total - reservas_activas; -1 si cupo_total=0 (sin límite)
    notas_registradas: int
    model_config = ConfigDict(extra='forbid')

class MetricasPanel(BaseModel):
    total_alumnos_cargados : int   # total convocados en todas las evaluaciones activas del tenant
    instancias_activas     : int   # total evaluaciones no eliminadas del tenant
    reservas_activas       : int   # total reservas activas del tenant
    notas_registradas      : int   # total resultados del tenant
    model_config = ConfigDict(extra='forbid')

class ConvocadoImportRow(BaseModel):
    nombre    : str     # min_length=1
    apellidos : str     # min_length=1
    email     : str     # min_length=1 — se cifra en el servicio
    usuario_id: UUID | None = None
    model_config = ConfigDict(extra='forbid')

class ConvocadoImportRequest(BaseModel):
    filas: list[ConvocadoImportRow]  # min_length=1
    model_config = ConfigDict(extra='forbid')

class ConvocadoImportResponse(BaseModel):
    insertados : int
    model_config = ConfigDict(extra='forbid')
```

## Criterios de aceptación

- [ ] `evaluacion` en DB con columnas y constraints según spec.
- [ ] `convocado_evaluacion` en DB con columnas y constraints según spec.
- [ ] `tipo` usa `create_type=False` — no crea ni elimina el ENUM en 012.
- [ ] `unique constraint` impide duplicar `(materia, cohorte, tipo, instancia)` en el mismo tenant.
- [ ] `cupo_total = 0` se interpreta como sin límite en el servicio (nunca rechaza por cupo).
- [ ] `bulk_create` es idempotente: reinsertar el mismo `usuario_id` no duplica.
- [ ] Schemas con `extra='forbid'` rechazan campos no declarados.
- [ ] `dias_disponibles` rechaza valores < 1 en schema (Pydantic `ge=1`).
- [ ] `email` de `ConvocadoEvaluacion` no se expone en texto plano en ninguna respuesta.
