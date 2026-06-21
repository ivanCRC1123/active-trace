# Spec: tareas-router (estructura de código y registro)

## Objetivo

Definir la estructura de archivos, capas y el contrato del router para C-16. No hay
lógica de negocio aquí — cada capa tiene su responsabilidad estricta.

## Archivos nuevos

| Archivo | Capa | Responsabilidad |
|---------|------|----------------|
| `backend/app/models/tarea.py` | Model | SQLAlchemy ORM — tabla `tarea` |
| `backend/app/models/comentario_tarea.py` | Model | SQLAlchemy ORM — tabla `comentario_tarea` |
| `backend/app/repositories/tarea_repository.py` | Repository | Queries async con scope de tenant |
| `backend/app/repositories/comentario_tarea_repository.py` | Repository | Queries de hilo |
| `backend/app/services/tarea_service.py` | Service | Lógica de negocio, FSM, membership check |
| `backend/app/schemas/tareas.py` | Schema | Pydantic v2, `extra='forbid'` |
| `backend/app/api/v1/routers/tareas.py` | Router | FastAPI endpoints, guards, DI |
| `backend/alembic/versions/0NN_tarea_comentario_tarea.py` | Migration | DDL de ambas tablas |
| `backend/tests/test_tareas.py` | Tests | ~50 tests de integración |

## Router — `backend/app/api/v1/routers/tareas.py`

```python
router = APIRouter(prefix="/api/v1/tareas", tags=["tareas"])

@router.get("/mis-tareas")
async def get_mis_tareas(
    filtros: MisTareasFiltros = Depends(),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TareaResponse]:
    ...

@router.post("", status_code=201)
async def crear_tarea(
    payload: TareaCreateRequest,
    current_user: CurrentUser = Depends(require_permission("tareas_internas:gestionar")),
    session: AsyncSession = Depends(get_session),
) -> TareaResponse:
    ...

@router.get("/{tarea_id}")
async def get_tarea(
    tarea_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TareaResponse:
    ...

@router.patch("/{tarea_id}/estado")
async def cambiar_estado(
    tarea_id: UUID,
    payload: TareaEstadoRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TareaResponse:
    ...

@router.get("")
async def list_tareas(
    filtros: TareaFiltros = Depends(),
    current_user: CurrentUser = Depends(require_permission("tareas_internas:gestionar")),
    session: AsyncSession = Depends(get_session),
) -> list[TareaResponse]:
    ...

@router.post("/{tarea_id}/comentarios", status_code=201)
async def agregar_comentario(
    tarea_id: UUID,
    payload: ComentarioCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ComentarioResponse:
    ...

@router.get("/{tarea_id}/comentarios")
async def get_comentarios(
    tarea_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ComentarioResponse]:
    ...
```

**Nota sobre `require_permission`**: los endpoints que usan `get_current_user` delegan la
verificación de membresía/FSM al service — el router solo establece quién está autenticado.
Los endpoints que usan `require_permission("tareas_internas:gestionar")` resuelven el scope
(own/all) en el service.

## Service — `backend/app/services/tarea_service.py`

Nunca accede directamente a la DB. Llama únicamente a:
- `TareaRepository`
- `ComentarioTareaRepository`
- `AsignacionRepository` (para verificar scope=own del PROFESOR)
- `AuditService` (para escribir audit log)

Métodos públicos:
```python
class TareaService:
    async def mis_tareas(usuario_id, tenant_id, filtros) -> list[TareaResponse]
    async def crear_tarea(tenant_id, payload, current_user, scope) -> TareaResponse
    async def get_tarea(tarea_id, tenant_id, current_user) -> TareaResponse
    async def cambiar_estado(tarea_id, tenant_id, nuevo_estado, current_user) -> TareaResponse
    async def list_tareas(tenant_id, filtros, current_user, scope) -> list[TareaResponse]
    async def agregar_comentario(tarea_id, tenant_id, texto, current_user) -> ComentarioResponse
    async def list_comentarios(tarea_id, tenant_id, current_user) -> list[ComentarioResponse]
```

## Repositories

### `TareaRepository`

Métodos necesarios:
- `list_by_asignado_a(usuario_id, tenant_id, filtros) → Sequence[TareaConUsuarios]`
- `list_tareas(tenant_id, filtros) → Sequence[TareaConUsuarios]`  ← acepta scope_user_id opcional
- `get_by_id(tarea_id, tenant_id) → TareaConUsuarios | None`
- `create(tarea: Tarea) → Tarea`
- `update_estado(tarea: Tarea, nuevo_estado: str) → Tarea`
- `soft_delete(tarea: Tarea) → None`

`TareaConUsuarios` es un named tuple/dataclass con joins resueltos (nombres de asignado_a y
asignado_por). Nunca expone email_cifrado.

### `ComentarioTareaRepository`

- `list_by_tarea(tarea_id, tenant_id) → Sequence[ComentarioConAutor]`  ← orden ASC creado_at
- `create(comentario: ComentarioTarea) → ComentarioTarea`

## Registro en main.py

```python
from app.api.v1.routers import tareas
app.include_router(tareas.router)
```

## Criterios de aceptación del router

- [ ] Todos los endpoints registrados bajo `/api/v1/tareas/`.
- [ ] `GET /mis-tareas` no tiene `require_permission` en el router — solo `get_current_user`.
- [ ] `POST /tareas` tiene `require_permission("tareas_internas:gestionar")`.
- [ ] `GET /tareas` tiene `require_permission("tareas_internas:gestionar")`.
- [ ] Endpoints de detalle, estado y comentarios usan solo `get_current_user` en el router.
- [ ] Service implementa toda la lógica de membership/FSM/scope — el router no tiene condicionales de negocio.
- [ ] Ningún Service llama directamente a `session.execute()` — todo va por Repository.
- [ ] Schemas con `extra='forbid'` en todos los modelos.
- [ ] ≤500 LOC en cada archivo de backend.
