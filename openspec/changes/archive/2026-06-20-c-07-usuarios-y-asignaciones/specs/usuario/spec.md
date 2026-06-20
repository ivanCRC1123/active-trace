# Spec: Usuario (E4)

## Entidad

Extiende la tabla `user` existente (auth, C-02/C-03). No es una tabla separada.

## Campos

| Campo | Tipo DB | Nullable | Cifrado | Notas |
|-------|---------|----------|---------|-------|
| id | UUID PK | no | no | gen_random_uuid() |
| tenant_id | UUID FK→tenant | no | no | CASCADE |
| nombre | VARCHAR(255) | no | no | |
| apellidos | VARCHAR(255) | no | no | renombrado desde `apellido` |
| email_cifrado | TEXT | no | **AES-256-GCM** | EncryptedString TypeDecorator |
| email_hash | VARCHAR(64) | no | HMAC-SHA256 | blind index — lookup de login |
| password_hash | TEXT | no | no | Argon2id |
| is_active | BOOLEAN | no | no | estado funcional (Activo/Inactivo) |
| dni_cifrado | TEXT | yes | **AES-256-GCM** | EncryptedString TypeDecorator |
| cuil_cifrado | TEXT | yes | **AES-256-GCM** | EncryptedString TypeDecorator |
| cbu_cifrado | TEXT | yes | **AES-256-GCM** | EncryptedString TypeDecorator |
| alias_cbu_cifrado | TEXT | yes | **AES-256-GCM** | EncryptedString TypeDecorator |
| banco | VARCHAR(255) | yes | no | nombre del banco |
| regional | VARCHAR(255) | yes | no | regional institucional |
| legajo | VARCHAR(100) | yes | no | legajo docente (atributo, no credencial) |
| legajo_profesional | VARCHAR(100) | yes | no | |
| facturador | BOOLEAN | no | no | DEFAULT false |
| created_at | TIMESTAMP | no | no | |
| updated_at | TIMESTAMP | no | no | trigger ON UPDATE |
| deleted_at | TIMESTAMP | yes | no | NULL = no borrado |

## Constraints

- `UNIQUE (tenant_id, email_hash)` — unicidad de email por tenant (via blind index)
- `INDEX (email_hash)` — lookup rápido por hash en login
- `deleted_at IS NULL` — filas activas (soft delete)

## Invariantes de negocio

- Identidad por UUID interno (RN-25). El `legajo` es un dato de negocio, no un selector de sesión.
- **Todos los PII están cifrados en DB**: email, dni, cuil, cbu, alias_cbu.
- `email_hash` (HMAC-SHA256) permite el lookup de login sin exponer plaintext en la DB.
- El service siempre recibe `email` plaintext → deriva internamente `email_cifrado` y `email_hash`.
- `is_active=False` = Inactivo. El usuario no puede autenticarse pero sus datos se conservan.
- Soft delete (`deleted_at ≠ NULL`) elimina lógicamente. Los queries de listado filtran `deleted_at IS NULL`.
- No se puede soft-delete un Usuario con asignaciones vigentes (400 — OQ-C07-2 cerrada).

## Datos bancarios (RN-26)

Los campos `cbu_cifrado`, `alias_cbu_cifrado`, `banco` son requeridos para el módulo de liquidaciones (C-18).
Son opcionales en C-07 (nullable) pero el servicio de liquidación verificará su presencia.

## Escenarios

### Creación
```
DADO que el ADMIN está autenticado
Y NO existe un usuario con email "nuevo@tenant.edu.ar" en su tenant
CUANDO POST /api/v1/admin/usuarios con nombre, apellidos, email, password, dni, cbu
ENTONCES 201 con UsuarioResponse.estado="Activo"
Y dni_cifrado en DB contiene ciphertext (no el valor plain)
Y UsuarioResponse.dni devuelve el valor plain original
```

```
DADO que el ADMIN está autenticado
Y YA existe un usuario con email "existente@tenant.edu.ar"
CUANDO POST /api/v1/admin/usuarios con el mismo email
ENTONCES 409 Conflict
```

```
DADO que el ADMIN de TENANT-A está autenticado
Y existe un usuario con email "docente@otro.edu.ar" en TENANT-B
CUANDO POST /api/v1/admin/usuarios con ese mismo email en TENANT-A
ENTONCES 201 (email en distintos tenants no es duplicado)
```

### Listado
```
DADO que el ADMIN está autenticado en su tenant
CUANDO GET /api/v1/admin/usuarios
ENTONCES solo devuelve usuarios de su propio tenant (sin deleted)
Y usuarios de otros tenants no aparecen
```

### Actualización
```
DADO que el ADMIN está autenticado
Y existe un usuario activo con id={uuid}
CUANDO PATCH /api/v1/admin/usuarios/{uuid} con estado="Inactivo"
ENTONCES 200 con estado="Inactivo"
Y is_active=False en DB
```

### Baja
```
DADO que el ADMIN está autenticado
Y existe un usuario sin asignaciones vigentes
CUANDO DELETE /api/v1/admin/usuarios/{uuid}
ENTONCES 204
Y GET /api/v1/admin/usuarios/{uuid} devuelve 404
Y deleted_at ≠ NULL en DB (soft delete)
```

```
DADO que el ADMIN está autenticado
Y el usuario tiene al menos una asignación con desde <= HOY AND (hasta IS NULL OR hasta >= HOY)
CUANDO DELETE /api/v1/admin/usuarios/{uuid}
ENTONCES 400 Bad Request con mensaje "tiene asignaciones vigentes"
```

### RBAC
```
DADO que un COORDINADOR (sin permiso usuarios:gestionar) está autenticado
CUANDO GET /api/v1/admin/usuarios
ENTONCES 403 Forbidden
```

## PII — Comportamiento esperado del cifrado

### Campos AES-256-GCM (`EncryptedString` TypeDecorator)
- `INSERT`: `process_bind_param("juan@tenant.edu.ar") → base64(nonce+ciphertext+tag)` → DB
- `SELECT`: `process_result_value(ciphertext_b64) → "juan@tenant.edu.ar"` → plaintext al servicio
- Dos INSERT del mismo email producen ciphertexts distintos (nonce aleatorio por AES-GCM)
- No es posible hacer `WHERE email_cifrado = encrypt('juan@...')` (correcto)

### Blind index (`email_hash` — HMAC-SHA256)
- `email_hash = hmac_email("Juan@Tenant.EDU.AR") = hmac_email("juan@tenant.edu.ar")` → mismo valor
- Determinístico: permite `WHERE email_hash = hmac_email(:input)` en el login
- Resistente a rainbow tables: clave = `ENCRYPTION_KEY` de 32 bytes (secreto del servidor)
- No revela el email aunque se filtre la DB: sin la clave HMAC, el hash no se invierte

### Login flow (C-03 actualizado)
```python
# auth/service.py
hash_input = email.strip().lower()
stmt = select(User).where(
    User.email_hash == hmac_email(hash_input),
    User.tenant_id == tenant_id,
    User.is_active == True,
    User.deleted_at.is_(None),
)
```
