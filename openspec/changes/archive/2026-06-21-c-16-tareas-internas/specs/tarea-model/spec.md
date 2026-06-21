# Spec: tarea-model (E12 — migración + modelos)

## Objetivo

Crear los modelos SQLAlchemy `Tarea` y `ComentarioTarea` (E12 del KB 04) y la migración Alembic
correspondiente. Es la base de persistencia de C-16.

## Modelos

### `Tarea` — `backend/app/models/tarea.py`

```python
class Tarea(Base):
    __tablename__ = "tarea"

    id: UUID           (PK, default uuid4)
    tenant_id: UUID    (FK → tenant.id, NOT NULL, index)
    materia_id: UUID   (FK → materia.id, nullable)
    asignado_a: UUID   (FK → user.id, NOT NULL, index)
    asignado_por: UUID (FK → user.id, NOT NULL, index)
    estado: str        (NOT NULL, default "Pendiente")
                       CHECK estado IN ('Pendiente','En progreso','Resuelta','Cancelada')
    descripcion: str   (NOT NULL, TEXT)
    contexto_id: UUID  (nullable — referencia blanda, SIN FK constraint)
    created_at: datetime  (utcnow, NOT NULL)
    updated_at: datetime  (utcnow, onupdate)
    deleted_at: datetime  (nullable — soft delete)
```

**Índices**:
- `ix_tarea_tenant_id` (tenant_id)
- `ix_tarea_asignado_a` (tenant_id, asignado_a) — más frecuente: "mis tareas"
- `ix_tarea_asignado_por` (tenant_id, asignado_por)
- `ix_tarea_estado` (tenant_id, estado)

**FK constraints**:
- `materia_id → materia.id` (nullable, ON DELETE SET NULL)
- `asignado_a → user.id` (NOT NULL, ON DELETE RESTRICT)
- `asignado_por → user.id` (NOT NULL, ON DELETE RESTRICT)
- `contexto_id`: ninguna FK — referencia blanda (ver D-C16-6)

**Sin `deleted_at` en FK**: soft delete en `Tarea` no afecta `ComentarioTarea`; los comentarios
quedan pero la tarea deja de aparecer en listados.

### `ComentarioTarea` — `backend/app/models/comentario_tarea.py`

```python
class ComentarioTarea(Base):
    __tablename__ = "comentario_tarea"

    id: UUID           (PK, default uuid4)
    tenant_id: UUID    (FK → tenant.id, NOT NULL, index)
    tarea_id: UUID     (FK → tarea.id, NOT NULL, index)
    autor_id: UUID     (FK → user.id, NOT NULL)
    texto: str         (NOT NULL, TEXT)
    creado_at: datetime (utcnow, NOT NULL)
    deleted_at: datetime (nullable — soft delete)
```

**Índice**: `ix_comentario_tarea_tarea_id` (tarea_id) — queries de hilo.

**Sin `updated_at`**: los comentarios son inmutables una vez creados (se puede soft-delete pero
no editar — auditoría append-only del hilo).

## Migración Alembic

**Nombre**: `0NN_tarea_comentario_tarea.py`

Orden de DDL:
1. `CREATE TABLE tarea (...)` — primero (sin FK a comentario_tarea)
2. `CREATE TABLE comentario_tarea (...)` — FK hacia tarea
3. Índices compuestos
4. `downgrade()`: DROP TABLE comentario_tarea → DROP TABLE tarea (inverso)

**Número real de migración**: asignar el siguiente disponible en `alembic/versions/`.

## Schemas Pydantic — `backend/app/schemas/tareas.py`

Todos con `model_config = ConfigDict(extra='forbid')`.

### Request schemas

```python
class TareaCreateRequest(BaseModel):
    asignado_a: UUID
    descripcion: str                     # min_length=1, max_length=2000
    materia_id: UUID | None = None
    contexto_id: UUID | None = None

class TareaEstadoRequest(BaseModel):
    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"]

class ComentarioCreateRequest(BaseModel):
    texto: str                           # min_length=1, max_length=4000
```

### Response schemas

```python
class UsuarioResumen(BaseModel):
    id: UUID
    nombre: str
    apellidos: str

class TareaResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    materia_id: UUID | None
    asignado_a: UsuarioResumen
    asignado_por: UsuarioResumen
    estado: str
    descripcion: str
    contexto_id: UUID | None
    created_at: datetime
    updated_at: datetime | None

class ComentarioResponse(BaseModel):
    id: UUID
    tarea_id: UUID
    autor: UsuarioResumen
    texto: str
    creado_at: datetime
```

### Filter schema (para listados)

```python
class TareaFiltros(BaseModel):
    asignado_a: UUID | None = None
    asignado_por: UUID | None = None
    materia_id: UUID | None = None
    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"] | None = None
    q: str | None = None                 # búsqueda libre sobre descripcion
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

class MisTareasFiltros(BaseModel):
    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"] | None = None
    materia_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
```

## Criterios de aceptación del modelo

- [ ] `tarea.contexto_id` no genera FK constraint en la BD (referencia blanda).
- [ ] `tarea.estado` tiene CHECK constraint con los 4 valores.
- [ ] `comentario_tarea.tarea_id` tiene FK a `tarea.id`.
- [ ] Soft delete funciona en ambas tablas (`deleted_at IS NOT NULL` excluye el row).
- [ ] `downgrade()` de la migración ejecuta sin error.
- [ ] Todos los schemas tienen `extra='forbid'`.

## Tests del modelo

- `test_tarea_crea_con_campos_minimos`: id, tenant_id, asignado_a, asignado_por, descripcion, estado='Pendiente'.
- `test_tarea_contexto_id_nullable_sin_fk`: insertar con contexto_id=uuid_inexistente no falla.
- `test_tarea_soft_delete`: `deleted_at` actualizado, row visible via raw query pero excluido de repo.
- `test_comentario_crea_hilo`: 3 comentarios sobre misma tarea, orden por creado_at.
- `test_comentario_soft_delete`: soft delete del comentario, no borra la tarea.
- `test_migracion_downgrade`: alembic downgrade borra ambas tablas limpiamente.
