# Spec: coloquios-router

## Objetivo

Router REST `coloquios.py`, seed del permiso `coloquios:gestionar` y registro en `main.py`.
Cubre todos los endpoints de gestión (COORDINADOR/ADMIN) y de reserva de turno (ALUMNO).

## Permiso nuevo: `coloquios:gestionar`

```python
# backend/scripts/seed_permissions.py — PERMISOS (catálogo):
{"codigo": "coloquios:gestionar", "modulo": "coloquios", "descripcion": "Gestionar convocatorias de evaluación (coloquios)"}

# PERMISSION_MATRIX["COORDINADOR"]:
"coloquios:gestionar": "all",

# PERMISSION_MATRIX["ADMIN"]:
"coloquios:gestionar": "all",
```

`evaluacion:reservar` (ya sembrado) no se modifica:
- ALUMNO → scope `all`
- ADMIN  → scope `all`

## Router (`backend/app/api/v1/routers/coloquios.py`)

```python
router = APIRouter(prefix="/api/v1/coloquios", tags=["coloquios"])

_PERM_GESTION  = require_permission("coloquios:gestionar")
_PERM_RESERVAR = require_permission("evaluacion:reservar")
```

### Endpoints de gestión (`coloquios:gestionar`)

```
GET    /                           list_convocatorias
                                   query: materia_id?, cohorte_id?, tipo?
                                   → list[EvaluacionResponse]   200

POST   /                           create_convocatoria
                                   body: EvaluacionCreate
                                   → EvaluacionResponse         201

GET    /metricas-panel             metricas_panel
                                   → MetricasPanel              200

GET    /{id}                       get_convocatoria
                                   → EvaluacionResponse         200

PATCH  /{id}                       update_convocatoria
                                   body: EvaluacionUpdate
                                   → EvaluacionResponse         200

DELETE /{id}                       delete_convocatoria
                                   → 204 No Content

POST   /{id}/convocados            importar_convocados
                                   body: ConvocadoImportRequest
                                   → ConvocadoImportResponse    200

GET    /{id}/metricas              metricas_convocatoria
                                   → MetricasConvocatoria       200

GET    /{id}/reservas              list_reservas_activas
                                   → list[ReservaResponse]      200

POST   /{id}/resultados            registrar_resultado
                                   body: ResultadoCreate
                                   → ResultadoResponse          201

GET    /{id}/resultados            list_resultados
                                   → list[ResultadoResponse]    200
```

### Endpoints de reserva de turno (`evaluacion:reservar`)

```
POST   /{id}/mis-reservas          reservar_turno
                                   body: ReservaCreate
                                   → ReservaResponse            201

DELETE /{id}/mis-reservas/{rid}    cancelar_reserva
                                   → ReservaResponse            200
```

## Mapeo ValueError → HTTPException

| `ValueError` mensaje       | HTTP  | Detalle                                      |
|----------------------------|-------|----------------------------------------------|
| `"not_found"`              | 404   | Convocatoria no encontrada                   |
| `"materia_not_found"`      | 404   | Materia no pertenece al tenant               |
| `"cohorte_not_found"`      | 404   | Cohorte no pertenece al tenant               |
| `"already_exists"`         | 409   | Ya existe convocatoria con esa combinación   |
| `"sin_cupo"`               | 409   | No hay cupos disponibles                     |
| `"reserva_already_active"` | 409   | El alumno ya tiene reserva activa            |
| `"reserva_already_cancelled"` | 409 | La reserva ya está cancelada                |
| `"alumno_not_found"`       | 404   | Alumno no pertenece al tenant                |

## Registro en `main.py`

```python
from app.api.v1.routers import coloquios
app.include_router(coloquios.router)
```

## Criterios de aceptación

### RBAC
- [ ] COORDINADOR → 200/201 en todos los endpoints de gestión.
- [ ] ADMIN → 200/201 en todos los endpoints de gestión y reserva.
- [ ] ALUMNO → 201 en `POST /{id}/mis-reservas`, 200 en `DELETE /{id}/mis-reservas/{rid}`.
- [ ] ALUMNO → 403 en cualquier endpoint de gestión (`/coloquios`, `/coloquios/{id}/convocados`, etc.).
- [ ] PROFESOR → 403 en endpoints de gestión; 200/201 en mis-reservas si tiene permiso.
- [ ] Sin autenticación → 401.

### Aislamiento multi-tenant
- [ ] COORDINADOR del tenant A no puede ver convocatorias del tenant B (404 en GET /{id}).
- [ ] ALUMNO del tenant A no puede reservar en convocatoria del tenant B (404).

### Comportamiento funcional
- [ ] `GET /metricas-panel` agrega correctamente: `total_alumnos_cargados`, `instancias_activas`,
     `reservas_activas`, `notas_registradas` solo del tenant del actor.
- [ ] `GET /{id}/metricas` devuelve: `convocados`, `reservas_activas`, `cupos_libres`,
     `notas_registradas` para esa evaluacion.
- [ ] `POST /{id}/convocados` acepta lote; devuelve `insertados`.
- [ ] `POST /{id}/resultados` con alumno_id que ya tiene resultado → reemplaza (soft-delete + 201).
- [ ] Todos los endpoints de gestión devuelven 404 si `{id}` es de otro tenant.
