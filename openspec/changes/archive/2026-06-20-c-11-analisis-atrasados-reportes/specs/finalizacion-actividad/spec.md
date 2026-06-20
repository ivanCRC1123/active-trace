# Spec: finalizacion-actividad — Modelo, Parser e Import (F1.2)

## Propósito

Persiste el estado de finalización de actividades por alumno, importado desde el reporte de
finalización del LMS. Es la base de datos de la query "sin corregir" (RN-07/08) y puede
complementar el análisis de atrasados en el futuro.

---

## Modelo SQLAlchemy: `FinalizacionActividad`

**Archivo**: `backend/app/models/finalizacion_actividad.py`

```python
class FinalizacionActividad(Base, BaseEntityMixin):
    __tablename__ = "finalizacion_actividad"

    entrada_padron_id: Mapped[UUID]  # FK → entrada_padron RESTRICT NOT NULL
    materia_id: Mapped[UUID]         # FK → materia RESTRICT NOT NULL
    asignacion_id: Mapped[UUID]      # FK → asignacion RESTRICT NOT NULL (scope, RN-04)
    actividad: Mapped[str]           # VARCHAR(500) NOT NULL
    finalizado: Mapped[bool]         # BOOLEAN NOT NULL DEFAULT FALSE
```

El mixin `BaseEntityMixin` ya provee: `id` (UUID PK), `tenant_id` (FK → tenant CASCADE),
`created_at`, `updated_at`, `deleted_at`.

**Restricciones** (en migración, no en ORM):
- `UNIQUE (entrada_padron_id, actividad, asignacion_id) WHERE deleted_at IS NULL` — permite
  re-importar como upsert (soft-delete + insert) sin violar la unicidad.

---

## Parser: `finalizacion_parser.py`

**Archivo**: `backend/app/services/finalizacion_parser.py`

### Contrato público

```python
class FinalizacionRow(TypedDict):
    email: str
    actividades: dict[str, bool]   # actividad → finalizado (True/False)

class ParsedFinalizacionFile(TypedDict):
    filas: list[FinalizacionRow]
    actividades_detectadas: list[str]
    warnings: list[str]

def parse_finalizacion_file(content: bytes, filename: str) -> ParsedFinalizacionFile:
    """Parse an LMS completion report (xlsx / csv).

    Raises:
        ValueError: unrecognized format, missing email column, or empty file.
    """
```

### Lógica de clasificación de columnas

Columnas de infraestructura a ignorar (igual que `calificaciones_parser._STUDENT_INFO_HEADERS`):
importar y reutilizar `_STUDENT_INFO_HEADERS` desde `calificaciones_parser`.

Columnas de actividad: todo lo que NO es infraestructura ni email. El valor de cada celda
se normaliza a `bool` comparando contra `_COMPLETED_VALUES` (D-C11-10):

```python
_COMPLETED_VALUES: frozenset[str] = frozenset({
    "completado", "completed", "sí", "si", "yes", "true", "1",
    "finalizado", "finished", "done",
})

def _is_completed(raw: str) -> bool:
    return raw.strip().lower() in _COMPLETED_VALUES
```

### Deduplicación

Misma lógica que `calificaciones_parser`: primera ocurrencia de email gana, duplicados emiten warning.

---

## Repositorio: `FinalizacionRepository`

**Archivo**: `backend/app/repositories/finalizacion_repository.py`

```python
class FinalizacionRepository(BaseRepository[FinalizacionActividad]):

    async def vaciar_por_asignacion_materia(
        self, asignacion_id: UUID, materia_id: UUID
    ) -> int:
        """Soft-delete all finalizacion rows for (asignacion_id × materia_id)."""

    async def bulk_insert(
        self,
        rows: list[dict],   # {entrada_padron_id, materia_id, asignacion_id, actividad, finalizado}
    ) -> int:
        """Bulk insert FinalizacionActividad rows. Returns count inserted."""

    async def list_sin_corregir(
        self, materia_id: UUID, asignacion_id: UUID
    ) -> list[SinCorregirRow]:
        """Returns (entrada_padron_id, nombre, apellidos, actividad) for completado+sin calificacion."""
        # Ver D-C11-7 para la query completa.
```

---

## Endpoint: `importar-finalizacion`

**Path**: `POST /api/v1/analisis/{materia_id}/cohortes/{cohorte_id}/importar-finalizacion`

**Permiso**: `calificaciones:importar` (D-C11-9)

**Request**: `multipart/form-data` con campo `file` (xlsx o csv).

**Flujo en el servicio** (`AnalisisService.importar_finalizacion`):

1. Resuelve `asignacion_id` activa del usuario actual para `(materia_id, cohorte_id)`.
   - Si no existe → 404 `asignacion_not_found`.
2. Parsea el archivo con `finalizacion_parser.parse_finalizacion_file()`.
3. Resuelve `entrada_padron_id` por `email_hash` desde el padrón activo (mismo helper que C-10).
   - Filas sin match en el padrón emiten warning (no error).
4. `FinalizacionRepository.vaciar_por_asignacion_materia(asignacion_id, materia_id)`.
5. `FinalizacionRepository.bulk_insert(rows)`.
6. Audit `CALIFICACIONES_IMPORTAR` (código existente, reutilizado).

**Response** (`FinalizacionImportResult`):

```python
class FinalizacionImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actividades_detectadas: int
    entradas_procesadas: int
    finalizadas: int          # count(finalizado=True)
    no_vinculadas: int        # alumnos en archivo sin match en padrón
    sin_corregir_count: int   # count de "sin corregir" tras el import
    warnings: list[str]
```

**Errores**:
- `404` si la asignación no existe para ese usuario×materia×cohorte.
- `409` si no hay versión de padrón activa para `(materia_id, cohorte_id)`.
- `400` si el archivo no tiene columna de email o formato no soportado.

---

## Tests requeridos

**Archivo**: `backend/tests/test_finalizacion_parser.py` (unitarios, sin DB)

| Test | Verifica |
|------|---------|
| `test_parse_xlsx_basico` | Parsea xlsx con 2 actividades y 3 alumnos correctamente |
| `test_parse_csv_basico` | Parsea CSV con mismo contenido |
| `test_completed_values_case_insensitive` | "COMPLETADO", "Sí", "yes" → `True` |
| `test_no_email_column_raises` | Sin columna email → `ValueError` |
| `test_duplicate_email_warning` | Email duplicado → warning, primera fila gana |
| `test_all_activity_columns_detected` | Columnas no-infraestructura → en `actividades_detectadas` |

**Archivo**: `backend/tests/test_analisis.py` (integración con DB) — sección FinalizacionImport:

| Test | Verifica |
|------|---------|
| `test_import_finalizacion_ok` | Import exitoso, count correcto en DB |
| `test_import_finalizacion_sin_padron_409` | Sin versión padrón activa → 409 |
| `test_import_finalizacion_sin_asignacion_404` | Sin asignación del usuario → 404 |
| `test_import_finalizacion_es_destructivo` | Re-import soft-delete previas |
| `test_import_finalizacion_solo_asignacion_propia` | PROFESOR solo ve su asignacion_id |
| `test_import_finalizacion_rbac_403` | Sin permiso → 403 |
