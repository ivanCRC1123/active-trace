# Spec: Analisis Router y Permisos (C-11)

## Router

**Archivo**: `backend/app/api/v1/routers/analisis.py`

**Prefix**: `/api/v1/analisis`

**Tags**: `["analisis"]`

### Tabla de endpoints

| Método | Path | Permiso guard | Handler |
|--------|------|--------------|---------|
| POST | `/{materia_id}/cohortes/{cohorte_id}/importar-finalizacion` | `calificaciones:importar` scoped | `importar_finalizacion` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/atrasados` | `atrasados:ver` scoped | `get_atrasados` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/ranking` | `atrasados:ver` scoped | `get_ranking` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/reportes-rapidos` | `atrasados:ver` scoped | `get_reporte_rapido` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/notas-finales` | `atrasados:ver` scoped | `get_notas_finales` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/notas-finales/exportar` | `atrasados:ver` scoped | `exportar_notas_finales` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/sin-corregir` | `atrasados:ver` scoped | `get_sin_corregir` |
| GET | `/{materia_id}/cohortes/{cohorte_id}/sin-corregir/exportar` | `atrasados:ver` scoped | `exportar_sin_corregir` |
| GET | `/monitor` | `atrasados:ver` scoped | `get_monitor` |

### Estructura del router

```python
_PERM_IMPORTAR = require_permission("calificaciones:importar", scoped=True)
_PERM_VER = require_permission("atrasados:ver", scoped=True)

router = APIRouter(prefix="/api/v1/analisis", tags=["analisis"])

def _svc(db: AsyncSession) -> AnalisisService:
    return AnalisisService(db)

def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg in ("asignacion_not_found", "materia_not_found", "cohorte_not_found"):
        return HTTPException(status_code=404, detail=msg)
    if msg == "no_hay_padron_activo":
        return HTTPException(status_code=409, detail=msg)
    return HTTPException(status_code=400, detail=msg)
```

El CSV export retorna `Response(content=..., media_type="text/csv", headers={"Content-Disposition": ...})`.

---

## Registro en `main.py`

```python
from app.api.v1.routers.analisis import router as analisis_router
app.include_router(analisis_router)
```

---

## Permisos nuevos (seed)

**Archivo**: `backend/scripts/seed_permissions.py`

Agregar al seed el permiso `atrasados:ver` y asignarlo a los roles correspondientes:

| Rol | Scope |
|-----|-------|
| TUTOR | own |
| PROFESOR | own |
| COORDINADOR | all |
| ADMIN | all |

El permiso `calificaciones:importar` para `importar-finalizacion` ya existe desde C-10 —
no requiere cambios en el seed.

**Formato del seed** (reutilizar el patrón existente):

```python
PERMISOS_C11 = [
    ("atrasados:ver", "Ver análisis de atrasados y reportes"),
]

ROL_PERMISOS_C11 = [
    # (rol_nombre, permiso, scope)
    ("TUTOR",       "atrasados:ver", "own"),
    ("PROFESOR",    "atrasados:ver", "own"),
    ("COORDINADOR", "atrasados:ver", "all"),
    ("ADMIN",       "atrasados:ver", "all"),
]
```

---

## `conftest.py` — limpieza de tablas

Actualizar el autouse fixture de limpieza (el que hace `DELETE FROM` en orden FK-safe)
para incluir `finalizacion_actividad` antes de `entrada_padron`:

```
calificacion → finalizacion_actividad → umbral_materia → entrada_padron → version_padron
```

---

## LOC estimado por archivo

| Archivo | Est. LOC |
|---------|----------|
| `analisis.py` (router) | ~150 |
| `analisis_service.py` | ~250 |
| `analisis_repository.py` | ~300 |
| `finalizacion_repository.py` | ~120 |
| `analisis.py` (schemas) | ~120 |
| `finalizacion_actividad.py` (model) | ~40 |
| `finalizacion_parser.py` | ~100 |

Todos dentro del límite de 500 LOC (regla dura §15).
