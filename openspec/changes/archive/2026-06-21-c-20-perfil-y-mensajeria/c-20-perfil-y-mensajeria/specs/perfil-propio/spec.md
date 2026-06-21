# Spec: Perfil propio (F11.1)

## Endpoints

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| `GET` | `/api/v1/perfil` | JWT (cualquier autenticado) | Lee perfil propio |
| `PATCH` | `/api/v1/perfil` | JWT (cualquier autenticado) | Actualiza campos editables |

La identidad del usuario proviene **exclusivamente** del JWT verificado (`current_user.id`).
No hay `{user_id}` en la URL — un usuario solo puede acceder a su propio perfil.

---

## Schema `PerfilResponse`

```python
class PerfilResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: UUID
    tenant_id: UUID
    nombre: str
    apellidos: str
    email: str           # plaintext (EncryptedString TypeDecorator descifra)
    sexo: str | None     # (solo si D-C20-1 = Opción A)
    dni: str | None      # plaintext
    cuil: str | None     # plaintext — SOLO LECTURA (no aparece en PerfilUpdate)
    cbu: str | None      # plaintext
    alias_cbu: str | None
    banco: str | None
    regional: str | None
    legajo: str | None         # SOLO LECTURA
    legajo_profesional: str | None
    facturador: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

---

## Schema `PerfilUpdate`

Todos los campos son opcionales (PATCH semántico). Los campos ausentes no se modifican.

```python
class PerfilUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    nombre: str | None = None
    apellidos: str | None = None
    email: EmailStr | None = None   # actualización especial — ver D-C20-2
    sexo: str | None = None         # (solo si D-C20-1 = Opción A)
    dni: str | None = None
    cbu: str | None = None
    alias_cbu: str | None = None
    banco: str | None = None
    regional: str | None = None
    legajo_profesional: str | None = None
    facturador: bool | None = None
    # cuil: AUSENTE — no es editable por el usuario (D-C20-6)
    # legajo: AUSENTE — asignado por ADMIN
```

---

## `PerfilService`

Archivo: `backend/app/services/perfil_service.py`

```
PerfilService(
    session: AsyncSession,
    tenant_id: UUID,
    repo: UsuarioRepository,
    audit: AuditService,
)

async get_propio(user_id: UUID) → User
async update_propio(user_id: UUID, data: PerfilUpdate) → User
    - Para email: llamar update_email() interno (D-C20-2)
    - Para otros PII: EncryptedString TypeDecorator maneja el re-cifrado
    - Auditoría: log PERFIL_EDITAR con campos_modificados
```

### Lógica de `update_propio()`

1. Cargar el usuario (`repo.get_by_id(user_id)`) — si no existe, 404 (no debería pasar con JWT válido).
2. Separar los campos del `PerfilUpdate` en dos grupos:
   - `email` → ruta especial (D-C20-2)
   - resto → actualización directa por `setattr` + `repo.update()`
3. Si se incluye `email`:
   a. Normalizar: `email.strip().lower()`
   b. Calcular `new_hash = hmac_email(normalized)`
   c. Verificar unicidad: `repo.get_by_email_hash(normalized)` — si existe Y no es el mismo usuario → 409
   d. Actualizar AMBOS: `email_cifrado = encrypt(normalized)`, `email_hash = new_hash`
4. Auditar: `PERFIL_EDITAR` con `detalle.campos_modificados` (nombres de campos, NO valores).

---

## `PerfilRepository`

No se crea un repositorio dedicado. `PerfilService` usa `UsuarioRepository` (ya existe en C-07).

---

## Router `/api/v1/perfil`

Archivo: `backend/app/api/v1/routers/perfil.py`

```
GET /api/v1/perfil
  Dep: get_current_user
  → service.get_propio(current_user.id)
  → 200 PerfilResponse

PATCH /api/v1/perfil
  Dep: get_current_user, body: PerfilUpdate
  → service.update_propio(current_user.id, data)
  → 200 PerfilResponse
  → 409 si email duplicado en tenant
  → 422 si validación Pydantic falla
```

---

## Invariantes de negocio

- **Self-only**: el usuario edita su propio perfil. `current_user.id == target`. No hay cross-user.
- **CUIL inmutable**: rechazado por schema (`extra='forbid'` + campo ausente en PerfilUpdate).
- **Email atómico**: cualquier actualización de email actualiza SIEMPRE ambos campos cifrado+hash.
- **PII en logs**: los campos cifrados (email, dni, cbu, alias_cbu) NUNCA aparecen en el `detalle`
  del AuditLog. Solo los nombres de los campos modificados.
- **Auditoría**: toda llamada exitosa a PATCH genera un registro en AuditLog (`PERFIL_EDITAR`).

---

## Códigos de auditoría — adición

En `backend/app/core/audit_codes.py`:

```python
# C-20 — perfil
PERFIL_EDITAR = "PERFIL_EDITAR"
```

Y en `VALID_ACTION_CODES`:
```python
PERFIL_EDITAR,
```

---

## Escenarios

### Ver perfil propio
```
DADO que el PROFESOR está autenticado
CUANDO GET /api/v1/perfil
ENTONCES 200 con PerfilResponse
Y email devuelto es el plaintext (no el ciphertext de DB)
Y cuil devuelto es el plaintext (solo lectura)
```

### Editar nombre
```
DADO que el TUTOR está autenticado
CUANDO PATCH /api/v1/perfil con {"nombre": "Nuevo Nombre"}
ENTONCES 200 con PerfilResponse.nombre = "Nuevo Nombre"
Y AuditLog contiene PERFIL_EDITAR con detalle.campos_modificados = ["nombre"]
```

### Editar email — éxito
```
DADO que el PROFESOR está autenticado
Y NO existe otro usuario con email "nuevo@tenant.edu.ar" en su tenant
CUANDO PATCH /api/v1/perfil con {"email": "nuevo@tenant.edu.ar"}
ENTONCES 200
Y DB.user.email_cifrado ≠ valor anterior (nuevo ciphertext)
Y DB.user.email_hash = hmac_email("nuevo@tenant.edu.ar")
Y login con email nuevo funciona (C-03)
Y login con email viejo falla (C-03)
Y AuditLog.detalle.cambio_email = true
```

### Editar email — duplicado en tenant
```
DADO que el PROFESOR está autenticado
Y EXISTE otro usuario con email "tomado@tenant.edu.ar" en su tenant
CUANDO PATCH /api/v1/perfil con {"email": "tomado@tenant.edu.ar"}
ENTONCES 409 Conflict
Y el email del usuario NO cambia en DB
```

### Editar email — mismo usuario, mismo email (no-op)
```
DADO que el PROFESOR está autenticado con email "propio@tenant.edu.ar"
CUANDO PATCH /api/v1/perfil con {"email": "propio@tenant.edu.ar"}
ENTONCES 200 (no error, no-op funcional)
Y AuditLog.detalle.campos_modificados puede omitir "email" (sin cambio real)
```

### Intentar editar CUIL
```
DADO que cualquier usuario autenticado
CUANDO PATCH /api/v1/perfil con {"cuil": "20-12345678-9"}
ENTONCES 422 Unprocessable Entity (campo no permitido — extra='forbid')
```

### Editar datos bancarios
```
DADO que el PROFESOR está autenticado
CUANDO PATCH /api/v1/perfil con {"cbu": "0720461188000012345678", "banco": "Santander"}
ENTONCES 200
Y DB.user.cbu_cifrado contiene el ciphertext del nuevo CBU
Y PerfilResponse.cbu = "0720461188000012345678" (plaintext)
Y AuditLog.detalle.campos_modificados = ["cbu", "banco"]
Y NO aparecen valores PII en el AuditLog
```

### Sin autenticación
```
DADO que no hay JWT en la petición
CUANDO GET /api/v1/perfil
ENTONCES 401 Unauthorized
```

### Aislamiento multi-tenant
```
DADO que el PROFESOR del TENANT-A está autenticado
CUANDO GET /api/v1/perfil
ENTONCES solo puede ver su propio perfil (tenant_id del JWT coincide con user.tenant_id)
Y no puede acceder al perfil de un usuario de TENANT-B bajo ninguna URL
```
