# Spec: Router /api/v1/asignaciones

## Prefijo y Tags

```python
router = APIRouter(prefix="/api/v1", tags=["asignaciones"])
```

## RBAC

Todos los endpoints requieren `require_permission("equipos:asignar")`.
- COORDINADOR y ADMIN tienen este permiso con scope=all (semilla de C-04).
- Cualquier otro rol → 403 Forbidden.

## Identidad

El `tenant_id` se extrae siempre del token JWT verificado (`current_user.tenant_id`).
JAMÁS del body, URL o headers.

## Endpoints

### GET /api/v1/asignaciones

Lista asignaciones del tenant. Soporta filtro de vigencia.

**Query params**:
- `vigente: bool | None` (opcional)
  - `true` → solo vigentes (`desde <= HOY AND (hasta IS NULL OR hasta >= HOY)`)
  - `false` → solo vencidas
  - omitido → todas (sin filtro de vigencia)

**Response 200**:
```json
[
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "usuario_id": "uuid",
    "rol_id": "uuid",
    "materia_id": "uuid | null",
    "carrera_id": "uuid | null",
    "cohorte_id": "uuid | null",
    "comisiones": ["string"],
    "responsable_id": "uuid | null",
    "desde": "date",
    "hasta": "date | null",
    "estado_vigencia": "Vigente | Vencida",
    "created_at": "datetime",
    "updated_at": "datetime"
  }
]
```

### POST /api/v1/asignaciones

Crea una nueva asignación.

**Request body** (`AsignacionCreate`):
```json
{
  "usuario_id": "uuid (required)",
  "rol_id": "uuid (required)",
  "materia_id": "uuid | null",
  "carrera_id": "uuid | null",
  "cohorte_id": "uuid | null",
  "comisiones": ["string"] ,
  "responsable_id": "uuid | null",
  "desde": "date (required)",
  "hasta": "date | null"
}
```

**Response 201**: `AsignacionResponse`

**Errores**:
- `404 Not Found` — `usuario_id`, `rol_id`, `materia_id`, `carrera_id`, `cohorte_id` o `responsable_id` no existe en el tenant
- `400 Bad Request` — rol es ALUMNO, o `desde > hasta`
- `422` — campos requeridos faltantes

### GET /api/v1/asignaciones/{id}

Obtiene una asignación por UUID.

**Response 200**: `AsignacionResponse`

**Errores**:
- `404 Not Found` — id no existe en el tenant O fue soft-deleted

### PATCH /api/v1/asignaciones/{id}

Actualiza campos de la asignación (partial update). Útil para extender o cerrar vigencia.

**Request body** (`AsignacionUpdate`, todos opcionales):
```json
{
  "materia_id": "uuid | null",
  "carrera_id": "uuid | null",
  "cohorte_id": "uuid | null",
  "comisiones": ["string"] | null,
  "responsable_id": "uuid | null",
  "desde": "date | null",
  "hasta": "date | null"
}
```

**Nota**: `usuario_id` y `rol_id` no son actualizables post-creación. Si cambia el rol, se debe
crear una nueva asignación y cerrar la existente (hasta = hoy - 1).

**Response 200**: `AsignacionResponse` actualizado

**Errores**:
- `404` — id no existe
- `400` — `desde > hasta`

### DELETE /api/v1/asignaciones/{id}

Soft-delete de la asignación.

**Response 204** — sin body

**Errores**:
- `404 Not Found` — id no existe en el tenant

## Tenant Isolation

El service y el repository garantizan que todos los queries filtran por `tenant_id`.
Un COORDINADOR de TENANT-A no puede ver ni modificar asignaciones de TENANT-B.
Los `usuario_id`, `rol_id`, `materia_id`, `carrera_id`, `cohorte_id` referenciados
deben pertenecer al mismo tenant.

## estado_vigencia en la Response

El campo `estado_vigencia` es calculado en el servicio antes de construir el response.
No existe como columna en la DB.

```python
# En AsignacionService
def _compute_estado_vigencia(self, desde: date, hasta: date | None) -> str:
    today = date.today()
    if desde > today:
        return "Vencida"
    if hasta is not None and hasta < today:
        return "Vencida"
    return "Vigente"
```

Se inyecta en la respuesta vía `model_validate`:
```python
response_data = asignacion.__dict__ | {"estado_vigencia": estado_vigencia}
return AsignacionResponse.model_validate(response_data)
```

## Error Responses

```json
{"detail": "mensaje descriptivo"}
```

Mapeo:
| ValueError message | HTTP status |
|--------------------|-------------|
| "not found" | 404 |
| "rol ALUMNO no es asignable" | 400 |
| "desde > hasta" | 400 |
