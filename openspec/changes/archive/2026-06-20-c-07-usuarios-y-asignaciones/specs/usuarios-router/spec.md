# Spec: Router /api/v1/admin/usuarios

## Prefijo y Tags

```python
router = APIRouter(prefix="/api/v1/admin", tags=["usuarios"])
```

## RBAC

Todos los endpoints requieren `require_permission("usuarios:gestionar")`.
- ADMIN tiene este permiso con scope=all (semilla de C-04).
- Cualquier otro rol → 403 Forbidden.

## Identidad

El `tenant_id` se extrae siempre del token JWT verificado (`current_user.tenant_id`).
JAMÁS del body, URL o headers.

## Endpoints

### GET /api/v1/admin/usuarios

Lista todos los usuarios del tenant actual (sin deleted, incluye is_active=False).

**Response 200**:
```json
[
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "nombre": "string",
    "apellidos": "string",
    "email": "string",
    "dni": "string | null",
    "cuil": "string | null",
    "cbu": "string | null",
    "alias_cbu": "string | null",
    "banco": "string | null",
    "regional": "string | null",
    "legajo": "string | null",
    "legajo_profesional": "string | null",
    "facturador": false,
    "estado": "Activo",
    "created_at": "datetime",
    "updated_at": "datetime"
  }
]
```

### POST /api/v1/admin/usuarios

Crea un nuevo usuario.

**Request body** (`UsuarioCreate`):
```json
{
  "nombre": "string (required)",
  "apellidos": "string (required)",
  "email": "string (required, valid email)",
  "password": "string (required)",
  "dni": "string | null",
  "cuil": "string | null",
  "cbu": "string | null",
  "alias_cbu": "string | null",
  "banco": "string | null",
  "regional": "string | null",
  "legajo": "string | null",
  "legajo_profesional": "string | null",
  "facturador": "bool (default false)"
}
```

**Response 201**: `UsuarioResponse`

**Errores**:
- `409 Conflict` — email ya existe en el tenant
- `422 Unprocessable Entity` — email inválido, campos requeridos faltantes

### GET /api/v1/admin/usuarios/{id}

Obtiene un usuario por su UUID.

**Response 200**: `UsuarioResponse`

**Errores**:
- `404 Not Found` — id no existe en el tenant O fue soft-deleted

### PATCH /api/v1/admin/usuarios/{id}

Actualiza campos del usuario (partial update). Campos no enviados no se modifican.

**Request body** (`UsuarioUpdate`, todos opcionales):
```json
{
  "nombre": "string | null",
  "apellidos": "string | null",
  "email": "string | null",
  "dni": "string | null",
  "cuil": "string | null",
  "cbu": "string | null",
  "alias_cbu": "string | null",
  "banco": "string | null",
  "regional": "string | null",
  "legajo": "string | null",
  "legajo_profesional": "string | null",
  "facturador": "bool | null",
  "estado": "Activo | Inactivo | null"
}
```

**Response 200**: `UsuarioResponse` actualizado

**Errores**:
- `404 Not Found` — id no existe en el tenant
- `409 Conflict` — nuevo email ya existe en el tenant

### DELETE /api/v1/admin/usuarios/{id}

Soft-delete del usuario.

**Response 204** — sin body

**Errores**:
- `404 Not Found` — id no existe en el tenant
- `400 Bad Request` — el usuario tiene asignaciones vigentes

## Tenant Isolation

El service y el repository garantizan que todos los queries filtran por `tenant_id`.
Un ADMIN de TENANT-A no puede ver, modificar ni eliminar usuarios de TENANT-B aunque conozca su UUID.

## Logging

PII nunca aparece en logs. Los logs incluyen solo: `user_id`, `tenant_id`, `action`, HTTP status.
El `email` tampoco aparece en logs — es PII cifrado en DB, solo visible en response desencriptada.

## Error Responses

Formato estándar FastAPI:
```json
{"detail": "mensaje descriptivo"}
```

Mapeo de errores de servicio:
| ValueError message | HTTP status |
|--------------------|-------------|
| "not found" | 404 |
| "email ya existe" | 409 |
| "tiene asignaciones vigentes" | 400 |
