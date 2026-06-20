# Spec: router-programas-y-fechas

## Objetivo

Dos `APIRouter` en un mismo archivo `backend/app/api/v1/routers/programas_y_fechas.py`, registrados en `main.py` con prefijos `/api/v1/programas` y `/api/v1/fechas-academicas`. Todos los endpoints requieren `estructura_academica:gestionar`.

## Permisos base

```python
_PERM_PROGRAMAS = require_permission("programas:gestionar")
_PERM_FECHAS    = require_permission("fechas_academicas:gestionar")
```

Ambos permisos son nuevos, sembrados para ADMIN + COORDINADOR. PROFESOR recibe 403.
`estructura_academica:gestionar` no se usa aquí (queda ADMIN-only para C-06).

## Endpoints — ProgramaMateria

```
router_programas = APIRouter(prefix="/api/v1/programas", tags=["programas"])
_PERM_PROGRAMAS = require_permission("programas:gestionar")

GET    /                    → list[ProgramaMateriaResponse]
  query: materia_id: UUID | None, carrera_id: UUID | None, cohorte_id: UUID | None

POST   /                    → ProgramaMateriaResponse  (status_code=201)
  body: ProgramaMateriaCreate

GET    /{id}                → ProgramaMateriaResponse
DELETE /{id}                → Response(status_code=204)   # soft delete

PATCH  /{id}                → ProgramaMateriaResponse
  body: ProgramaMateriaUpdate
```

**Errores mapeados:**
| ValueError del servicio | HTTP |
|-------------------------|------|
| `"materia not found"`   | 404  |
| `"carrera not found"`   | 404  |
| `"cohorte not found"`   | 404  |
| `"programa ya existe"`  | 409  |
| `"not found"`           | 404  |

## Endpoints — FechaAcademica

```
router_fechas = APIRouter(prefix="/api/v1/fechas-academicas", tags=["fechas-academicas"])

GET    /                          → list[FechaAcademicaResponse]
  query: materia_id: UUID | None, cohorte_id: UUID | None, periodo: str | None

POST   /                          → FechaAcademicaResponse  (status_code=201)
  body: FechaAcademicaCreate

GET    /fragmento-lms             → {"fragmento": str}
  query: materia_id: UUID, cohorte_id: UUID, periodo: str | None
  note: endpoint sin /{id}, antes de /{id} en el router para evitar conflicto de rutas

GET    /{id}                      → FechaAcademicaResponse
PATCH  /{id}                      → FechaAcademicaResponse
  body: FechaAcademicaUpdate
DELETE /{id}                      → Response(status_code=204)
```

**Errores mapeados:**
| ValueError del servicio       | HTTP |
|-------------------------------|------|
| `"materia not found"`         | 404  |
| `"cohorte not found"`         | 404  |
| `"fecha ya existe"`           | 409  |
| `"not found"`                 | 404  |

## Registro en `main.py`

```python
from app.api.v1.routers import programas_y_fechas

app.include_router(programas_y_fechas.router_programas)
app.include_router(programas_y_fechas.router_fechas)
```

## Convenciones

- El router delega toda lógica a `ProgramasService`. Sin lógica de negocio en el router.
- `router_programas` usa `_PERM_PROGRAMAS = require_permission("programas:gestionar")`.
- `router_fechas` usa `_PERM_FECHAS = require_permission("fechas_academicas:gestionar")`.
- `current_user, _scope = Depends(_PERM_*)` en cada endpoint; `tenant_id = current_user.tenant_id`.
- Errores `ValueError` del servicio → `HTTPException` con código apropiado.
- `404` para cualquier FK que no exista en el tenant (no revelar existencia en otro tenant).
- `409` para violaciones de unique constraint.
- El endpoint `GET /fechas-academicas/fragmento-lms` devuelve siempre 200, nunca 404 (fragmento vacío si no hay datos).

## Criterios de aceptación

- [ ] Ambos routers registrados en `main.py`; endpoints visibles en `/docs`.
- [ ] Todos los endpoints requieren `estructura_academica:gestionar` (ADMIN y COORDINADOR → 200; PROFESOR → 403).
- [ ] Sin lógica de negocio en el router; toda validación en `ProgramasService`.
- [ ] `GET /fragmento-lms` retorna 200 con `{"fragmento": ""}` cuando no hay fechas.
- [ ] Orden correcto de rutas: `/fragmento-lms` declarado antes de `/{id}` para evitar que FastAPI interprete "fragmento-lms" como un UUID.
- [ ] Tests de integración cubren happy path y casos de error para cada endpoint.
