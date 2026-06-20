# Spec: EntradaPadron (E6 — fila de padrón)

## Entidad

Representa un alumno dentro de una VersionPadron. El campo `usuario_id` es nullable: un alumno
puede aparecer en el padrón antes de tener cuenta en el sistema. Al importar, se intenta
auto-vincular por `email_hash` (D-C09-3).

## Campos

| Campo | Tipo DB | Nullable | Notas |
|-------|---------|----------|-------|
| id | UUID PK | no | gen_random_uuid() |
| version_id | UUID FK→version_padron | no | RESTRICT — la versión debe existir |
| tenant_id | UUID FK→tenant | no | CASCADE |
| usuario_id | UUID FK→user | yes | SET NULL — nullable hasta que el alumno tenga cuenta |
| nombre | VARCHAR(255) | no | |
| apellidos | VARCHAR(255) | no | |
| email_cifrado | TEXT | no | AES-256-GCM via EncryptedString TypeDecorator |
| email_hash | VARCHAR(64) | no | HMAC-SHA256(ENCRYPTION_KEY, normalize(email)) |
| comision | VARCHAR(255) | yes | grupo/sección del alumno en la materia |
| regional | VARCHAR(255) | yes | sede o regional institucional |
| created_at | TIMESTAMPTZ | no | |
| updated_at | TIMESTAMPTZ | no | trigger ON UPDATE |
| deleted_at | TIMESTAMPTZ | yes | NULL = no borrada |

## PII y cifrado

Reutiliza exactamente el mismo mecanismo de C-07 (`User.email_cifrado` + `User.email_hash`):

- `email_cifrado`: columna ORM con tipo `EncryptedString` (TypeDecorator en `app/models/base.py`).
  El servicio pasa el email en plaintext al constructor ORM; el TypeDecorator cifra en `process_bind_param`.
- `email_hash`: `hmac_email(email)` desde `app.core.encryption`. Se calcula explícitamente en el
  servicio antes de construir el objeto ORM (el TypeDecorator no lo deriva automáticamente).

```python
# En PadronService._build_entradas():
from app.core.encryption import hmac_email

EntradaPadron(
    version_id=version.id,
    tenant_id=tenant_id,
    usuario_id=await _resolve_usuario_id(row["email"], tenant_id, session),
    nombre=row["nombre"],
    apellidos=row["apellidos"],
    email_cifrado=row["email"],   # TypeDecorator cifra en write
    email_hash=hmac_email(row["email"]),
    comision=row.get("comision"),
    regional=row.get("regional"),
)
```

**Los emails NUNCA aparecen en logs.** Solo el `email_hash` puede loguearse para debugging.

## Auto-link (D-C09-3)

Al importar, para cada entrada se busca:
```python
select(User.id).where(
    User.tenant_id == tenant_id,
    User.email_hash == hmac_email(email),
    User.deleted_at.is_(None),
)
```
Si hay match: `usuario_id = user.id`. Si no: `usuario_id = None`.

El auto-link es best-effort: si el usuario existe con ese email, se vincula; si no, la entrada
queda sin vincular y se puede vincular manualmente después (feature futura).

## EntradaPadronRepository

Métodos requeridos:
- `list_by_version(version_id: UUID) → Sequence[EntradaPadron]` — todas las entradas de una versión
- `bulk_create(entradas: list[EntradaPadron]) → None` — inserta N entradas en un batch

## EntradaPadronResponse schema

```python
class EntradaPadronResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    version_id: UUID
    tenant_id: UUID
    usuario_id: UUID | None
    nombre: str
    apellidos: str
    email: str             # plaintext — decryptado por TypeDecorator en read
    comision: str | None
    regional: str | None
    vinculado: bool        # True si usuario_id is not None — derivado, no almacenado
    created_at: datetime
    updated_at: datetime
```

## Invariantes de negocio

- `tenant_id` de EntradaPadron DEBE coincidir con el `tenant_id` de su VersionPadron.
- `email` (normalizado: `strip().lower()`) debe ser único dentro de la misma `version_id`
  (el servicio deduplica antes del bulk insert; no es constraint de DB).
- `email`, `nombre` y `apellidos` son requeridos para cada entrada; filas sin estos campos
  se descartan con advertencia en el servicio.
- `usuario_id`, si se provee, debe pertenecer al mismo `tenant_id`.

## Índices

```sql
CREATE INDEX idx_entrada_padron_version
  ON entrada_padron(version_id) WHERE deleted_at IS NULL;

CREATE INDEX idx_entrada_padron_email_hash
  ON entrada_padron(tenant_id, email_hash) WHERE deleted_at IS NULL;

CREATE INDEX idx_entrada_padron_usuario
  ON entrada_padron(usuario_id)
  WHERE deleted_at IS NULL AND usuario_id IS NOT NULL;
```

## Escenarios

### Entrada con usuario vinculado
```
DADO que existe un User con email="alumno@uni.edu" en TENANT-A
Y se importa un padrón que incluye email="alumno@uni.edu"
ENTONCES EntradaPadron.usuario_id = user.id del User existente
Y EntradaPadronResponse.vinculado = True
```

### Entrada sin usuario (alumno sin cuenta)
```
DADO que NO existe ningún User con email="nuevo@uni.edu" en TENANT-A
Y se importa un padrón que incluye email="nuevo@uni.edu"
ENTONCES EntradaPadron.usuario_id = None
Y EntradaPadronResponse.vinculado = False
```

### Tenant isolation
```
DADO que existe un User con email="x@uni.edu" en TENANT-B
Y se importa un padrón en TENANT-A con email="x@uni.edu"
ENTONCES el auto-link NO se resuelve (el User es de otro tenant)
Y EntradaPadron.usuario_id = None
```

### Email duplicado en mismo archivo
```
DADO que el archivo tiene dos filas con el mismo email
CUANDO se procesa el import
ENTONCES una de las filas se descarta con advertencia "email duplicado: x@uni.edu — se conserva la primera ocurrencia"
Y solo se crea una EntradaPadron para ese email
```

### Email cifrado en DB
```
DADO que se importó un padrón con email="alumno@uni.edu"
CUANDO se consulta la DB directamente (psql)
ENTONCES la columna email_cifrado contiene ciphertext AES-256-GCM (no plaintext)
Y la columna email_hash contiene el HMAC-SHA256 (no el email)
Y GET /api/v1/padron/{mid}/cohortes/{cid} devuelve el email en plaintext (decryptado por TypeDecorator)
```
