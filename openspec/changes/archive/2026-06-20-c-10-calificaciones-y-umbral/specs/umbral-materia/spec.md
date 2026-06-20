# Spec: Repositorios y Schemas — Calificacion / UmbralMateria

## CalificacionRepository

Archivo: `backend/app/repositories/calificacion_repository.py`

```python
class CalificacionRepository(BaseRepository[Calificacion]):
    # Además de los métodos heredados de BaseRepository:

    async def list_by_materia_asignacion(
        self, materia_id: UUID, asignacion_id: UUID | None
    ) -> Sequence[Calificacion]:
        """
        scope=own: asignacion_id != None → filtra por asignacion_id.
        scope=all: asignacion_id = None → devuelve todas las calificaciones de la materia.
        """

    async def upsert_batch(self, calificaciones: list[Calificacion]) -> int:
        """
        Inserta o actualiza calificaciones por (entrada_padron_id, actividad, asignacion_id).
        Retorna la cantidad de filas afectadas.
        Usa INSERT ... ON CONFLICT DO UPDATE.
        """

    async def soft_delete_by_asignacion(
        self, materia_id: UUID, asignacion_id: UUID | None
    ) -> int:
        """
        scope=own: soft-delete con asignacion_id.
        scope=all (asignacion_id=None): soft-delete todas las de esa materia en el tenant.
        Retorna filas eliminadas.
        """

    async def list_by_entrada_padron(
        self, entrada_padron_id: UUID
    ) -> Sequence[Calificacion]:
        """Devuelve todas las calificaciones de un alumno específico."""
```

## UmbralMateriaRepository

Archivo: `backend/app/repositories/umbral_materia_repository.py`

```python
class UmbralMateriaRepository(BaseRepository[UmbralMateria]):

    async def get_by_asignacion_materia(
        self, asignacion_id: UUID, materia_id: UUID
    ) -> UmbralMateria | None:
        """Busca el umbral activo para (asignacion_id, materia_id)."""

    async def upsert(
        self, asignacion_id: UUID, materia_id: UUID, umbral_pct: int, valores_aprobatorios: list[str]
    ) -> UmbralMateria:
        """
        Si existe: actualiza umbral_pct y valores_aprobatorios.
        Si no existe: crea un nuevo UmbralMateria.
        """
```

## Schemas Pydantic

Archivo: `backend/app/schemas/calificaciones.py`

```python
# Todos con model_config = ConfigDict(extra="forbid")

class ActividadDetectada(BaseModel):
    nombre: str
    tipo: Literal["numerica", "textual"]
    total_notas: int            # filas con valor en esta columna

class AlumnoPreviewEntry(BaseModel):
    nombre: str
    apellidos: str
    # no se incluye email en preview (privacidad)

class CalificacionesPreview(BaseModel):
    actividades_detectadas: list[ActividadDetectada]
    alumnos_detectados: int
    advertencias: list[str]

class CalificacionesImportResult(BaseModel):
    actividades_importadas: int
    calificaciones_creadas: int
    calificaciones_actualizadas: int
    total_aprobadas: int
    advertencias: list[str]

class CalificacionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    entrada_padron_id: UUID
    materia_id: UUID
    asignacion_id: UUID | None
    actividad: str
    nota_numerica: Decimal | None
    nota_textual: str | None
    aprobado: bool
    origen: str
    importado_at: datetime
    created_at: datetime
    updated_at: datetime

class EntradaConCalificaciones(BaseModel):
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    calificaciones: list[CalificacionResponse]

class CalificacionesPorAlumno(BaseModel):
    """Respuesta de GET /calificaciones/{materia_id}/cohortes/{cohorte_id}"""
    materia_id: UUID
    cohorte_id: UUID
    asignacion_id: UUID | None
    total_alumnos: int
    alumnos: list[EntradaConCalificaciones]

class UmbralMateriaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    umbral_pct: int = Field(default=60, ge=1, le=100)
    valores_aprobatorios: list[str] = Field(
        default=["Satisfactorio", "Supera lo esperado"],
        min_length=1,
    )

class UmbralMateriaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID | None               # None si usa los defaults (no hay registro en DB)
    asignacion_id: UUID | None
    materia_id: UUID
    umbral_pct: int
    valores_aprobatorios: list[str]
    es_default: bool              # True si no hay registro en DB → usa los defaults

class SinCorregirEntry(BaseModel):
    nombre: str
    apellidos: str
    actividad: str
    # no se incluye email (privacidad)

class FinalizacionResult(BaseModel):
    """Respuesta de POST /calificaciones/.../importar-finalizacion"""
    total_sin_corregir: int
    actividades_afectadas: list[str]
    alumnos: list[SinCorregirEntry]
    advertencias: list[str]
```

## Nota sobre upsert en CalificacionRepository

El endpoint de importación puede llamarse múltiples veces con el mismo archivo (el docente
re-importa tras corregir el umbral). La restricción única en `(entrada_padron_id, actividad,
asignacion_id)` permite usar `INSERT ... ON CONFLICT (entrada_padron_id, actividad, asignacion_id)
WHERE deleted_at IS NULL DO UPDATE SET nota_numerica=EXCLUDED.nota_numerica, ...`. El servicio
reporta en el resultado cuántas fueron creadas y cuántas actualizadas.
