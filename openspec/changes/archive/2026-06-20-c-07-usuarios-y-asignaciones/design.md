# C-07 — Design Decisions

## D-C07-1: Usuario = auth `user` table extendida (misma tabla)

**Decisión**: No se crea una tabla `usuario` separada. La tabla `user` existente (auth, C-02/C-03)
se extiende con los campos PII y de perfil de E4.

**Justificación**:
- El audit log (C-05) y toda la infraestructura de auth ya referencian `user.id` como el
  identificador de persona en el sistema. Crear una tabla separada rompería esas referencias o
  requeriría un join costoso en cada acción autenticada.
- La KB define "la identidad es un UUID interno" (D2, RN-25) — ese UUID ES el `user.id`.
- El modelo `User` ya tiene `nombre`, `apellido`, `email`, `is_active`. Extenderlo es más simple
  que mantener dos entidades sincronizadas.

**Cambios en la tabla `user` (migración 006)**:
- `apellido` → renombrado a `apellidos` (E4 usa plural)
- Agregados (nullable, para no romper filas existentes):
  - `dni_cifrado TEXT`
  - `cuil_cifrado TEXT`
  - `cbu_cifrado TEXT`
  - `alias_cbu_cifrado TEXT`
  - `banco VARCHAR(255)`
  - `regional VARCHAR(255)`
  - `legajo VARCHAR(100)`
  - `legajo_profesional VARCHAR(100)`
  - `facturador BOOLEAN NOT NULL DEFAULT FALSE`

**Risk**: si en el futuro se requieren usuarios que NO tienen login (e.g., docentes importados
sin credenciales), se puede agregar un `user` con password_hash vacío + is_active=False +
flag `tiene_credenciales=False`. Por ahora, toda persona en el sistema tiene credenciales de acceso.

---

## D-C07-2: Email cifrado + blind index HMAC-SHA256 para lookup de login

**Decisión**: El campo `email` se cifra con AES-256-GCM (igual que DNI/CUIL/CBU) y se agrega
un blind index `email_hash` (HMAC-SHA256 del email normalizado) que permite el lookup de login
sin exponer el plaintext en la DB.

**Problema previo resuelto**: AES-GCM es no determinístico — el mismo plaintext produce
ciphertexts distintos por el nonce aleatorio. No se puede hacer `WHERE email_cifrado = encrypt(x)`.

**Solución — Blind Index pattern**:

| Campo | Tipo | Propósito |
|-------|------|-----------|
| `email_cifrado` | TEXT NOT NULL | Valor cifrado AES-256-GCM — para display/recover |
| `email_hash` | VARCHAR(64) NOT NULL | HMAC-SHA256(key, normalize(email)) — para lookup SQL |

- **Normalización**: `email.strip().lower()` antes de HMAC y de cifrar → case-insensitive.
- **Clave HMAC**: misma `settings.ENCRYPTION_KEY` (32 bytes). Mismo secreto, función diferente.
- **Unicidad**: `UNIQUE(tenant_id, email_hash)` reemplaza el antiguo `UNIQUE(tenant_id, email)`.
- **`email` plaintext**: la columna `email` existente se ELIMINA en migración 006.

**Función nueva en `backend/app/core/encryption.py`**:
```python
import hmac as _hmac
import hashlib

def hmac_email(email: str) -> str:
    """HMAC-SHA256 del email normalizado — blind index para lookup sin exponer plaintext."""
    key = settings.ENCRYPTION_KEY.encode("utf-8")
    normalized = email.strip().lower()
    return _hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
```

**Cambio en `backend/app/core/auth/service.py`** (C-03 — único punto de modificación):
```python
# Antes:
stmt = select(User).where(User.email == email, ...)
# Después:
stmt = select(User).where(User.email_hash == hmac_email(email.strip().lower()), ...)
```

**Impacto en fixtures existentes**:
- `conftest.py` y fixtures de tests C-02/C-03 crean users con `email=` directo.
- Tras migración 006, los campos son `email_cifrado` y `email_hash`.
- Los fixtures deben pasar ambos campos, o el service de creación de usuario los genera a partir
  del plaintext (opción más limpia: el service siempre recibe `email` plaintext y deriva ambos).

**Campos cifrados confirmados (AES-256-GCM) — 5 campos**:
`email_cifrado`, `dni_cifrado`, `cuil_cifrado`, `cbu_cifrado`, `alias_cbu_cifrado`

---

## D-C07-3: EncryptedString — TypeDecorator SQLAlchemy (cifrado transparente en ORM)

**Decisión**: Se implementa `EncryptedString(TypeDecorator)` en `backend/app/models/base.py` que
envuelve las funciones `encrypt/decrypt` ya existentes en `backend/app/core/encryption.py` (C-02).

```python
class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return decrypt(value) if value is not None else None
```

**Uso en el modelo**:
```python
dni_cifrado: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
```

**Ventajas**:
- El servicio trabaja con plaintext; el ORM se encarga de cifrar antes de INSERT/UPDATE y
  descifrar después de SELECT.
- No hay llamadas manuales a `encrypt/decrypt` dispersas en el código.
- Compatible con async SQLAlchemy (encrypt/decrypt son sync puras, sin I/O).

**Limitación documentada**: no se puede hacer `WHERE dni_cifrado = :val`. No necesitamos filtrar
por estos campos en ningún endpoint de C-07.

---

## D-C07-4: `estado` como vista sobre `is_active` (sin nuevo tipo enum en DB)

**Decisión**: E4 define `estado: Activo | Inactivo`. Se implementa como derivación de
`user.is_active: bool`, sin agregar columna nueva.

- `UsuarioResponse.estado` → `"Activo"` si `is_active=True`, `"Inactivo"` si `is_active=False`.
- `UsuarioUpdate.estado: EstadoUsuario | None` → el service traduce a `is_active`.
- El auth service existente sigue usando `is_active` directamente (sin cambios en C-03).

**Por qué no un nuevo enum en DB**: `is_active` es booleano y cumple exactamente la misma semántica
que un enum de dos valores. Agregar `estado_usuario VARCHAR` o un PostgreSQL ENUM sería redundante.

---

## D-C07-5: `asignacion.rol_id FK → rol` (no enum hardcodeado)

**Decisión**: `Asignacion.rol_id` es FK a la tabla `rol` existente (C-04), no un VARCHAR o Python
Enum con los valores PROFESOR/TUTOR/etc.

**Justificación**:
- Extensibilidad: nuevos roles se agregan al catálogo de `rol` sin cambiar el schema.
- Consistencia: el mismo catálogo de roles define tanto el RBAC (UserRol) como el contexto
  académico (Asignacion).
- El KB lista `PROFESOR | TUTOR | COORDINADOR | NEXO | ADMIN | FINANZAS` como valores actuales;
  el servicio valida que no se use `ALUMNO` en una asignación docente.

**Validación en servicio**:
```python
ALUMNO_ROL = "ALUMNO"  # nombre del rol excluido de asignaciones
if rol.nombre == ALUMNO_ROL:
    raise ValueError("el rol ALUMNO no es asignable a contextos docentes")
```

---

## D-C07-6: `comisiones` almacenado como JSONB `[]`

**Decisión**: `asignacion.comisiones` se almacena como JSONB con valor por defecto `'[]'`.

```python
comisiones: Mapped[list[str]] = mapped_column(
    sa.JSON(), nullable=False, server_default="'[]'"
)
```

**Por qué JSONB sobre `ARRAY(String)`**:
- `ARRAY` en asyncpg requiere codec personalizado para tipos no-nativos en migraciones.
- JSONB es soportado nativamente por SQLAlchemy y asyncpg sin configuración adicional.
- Permite `asignacion.comisiones @> '["MAT_A"]'` en queries futuras si es necesario.

---

## D-C07-7: `estado_vigencia` es computado, nunca almacenado (confirma S2 y D8)

**Decisión**: El campo `estado_vigencia: Vigente | Vencida` del KB **no existe** en la DB.
Se calcula en el service al momento de cada consulta.

```python
from datetime import date

def compute_estado_vigencia(desde: date, hasta: date | None) -> str:
    today = date.today()
    if desde > today:
        return "Vencida"   # aún no comenzó — no vigente
    if hasta is not None and hasta < today:
        return "Vencida"
    return "Vigente"
```

**Por qué no almacenar**:
- Evita inconsistencias entre el campo almacenado y las fechas.
- No requiere ningún job de actualización periódica.
- El KB lo marca explícitamente como "derivado" (E5).

`AsignacionResponse.estado_vigencia` es el único lugar donde aparece este valor.

---

## D-C07-8: Password requerida en creación vía ABM

**Decisión**: `POST /api/v1/admin/usuarios` requiere el campo `password` en el body.

ADMIN establece la contraseña inicial. El docente puede cambiarla luego con el flujo de
recuperación (ya implementado en C-03: `POST /api/auth/forgot-password` + `POST /api/auth/reset-password`).

**Alternativa descartada**: generar contraseña temporal y enviarla por email — requiere cola de
comunicaciones (C-12, no disponible aún).

---

## Migración 006 — Resumen

```
revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"   ← C-06 (005 carrera/cohorte/materia)

upgrade():
  # Extender tabla user — email: plaintext → cifrado + blind index
  op.alter_column("user", "apellido", new_column_name="apellidos")

  # Paso 1: agregar columnas nuevas como nullable (para data migration)
  op.add_column("user", sa.Column("email_cifrado", sa.Text(), nullable=True))
  op.add_column("user", sa.Column("email_hash", sa.String(64), nullable=True))

  # Paso 2: DATA MIGRATION — via script externo (scripts/migrate_006_email.py)
  #   Para cada fila en "user":
  #     email_cifrado = encrypt(email)
  #     email_hash    = hmac_email(email)
  #   Ejecutar ANTES de hacer NOT NULL.
  #   En dev/test: no hay filas reales, se puede saltar y dejar los fixtures que usen el nuevo schema.

  # Paso 3: hacer NOT NULL + unique
  op.alter_column("user", "email_cifrado", nullable=False)
  op.alter_column("user", "email_hash", nullable=False)
  op.create_unique_constraint("uq_user_tenant_email_hash", "user", ["tenant_id", "email_hash"])
  op.create_index("idx_user_email_hash", "user", ["email_hash"])

  # Paso 4: eliminar columna email plaintext
  op.drop_constraint("uq_user_tenant_email", "user", type_="unique")  # si existe
  op.drop_column("user", "email")

  # Resto de columnas PII
  op.add_column("user", sa.Column("dni_cifrado", sa.Text(), nullable=True))
  op.add_column("user", sa.Column("cuil_cifrado", sa.Text(), nullable=True))
  op.add_column("user", sa.Column("cbu_cifrado", sa.Text(), nullable=True))
  op.add_column("user", sa.Column("alias_cbu_cifrado", sa.Text(), nullable=True))
  op.add_column("user", sa.Column("banco", sa.String(255), nullable=True))
  op.add_column("user", sa.Column("regional", sa.String(255), nullable=True))
  op.add_column("user", sa.Column("legajo", sa.String(100), nullable=True))
  op.add_column("user", sa.Column("legajo_profesional", sa.String(100), nullable=True))
  op.add_column("user", sa.Column("facturador", sa.Boolean(), nullable=False, server_default="false"))

  # Crear tabla asignacion
  op.create_table("asignacion",
    sa.Column("id", PostgreSQL UUID, PK, server_default=gen_random_uuid()),
    sa.Column("tenant_id", UUID, FK→tenant.id CASCADE),
    sa.Column("usuario_id", UUID, FK→"user".id RESTRICT),
    sa.Column("rol_id", UUID, FK→rol.id RESTRICT),
    sa.Column("materia_id", UUID, FK→materia.id RESTRICT, nullable),
    sa.Column("carrera_id", UUID, FK→carrera.id RESTRICT, nullable),
    sa.Column("cohorte_id", UUID, FK→cohorte.id RESTRICT, nullable),
    sa.Column("comisiones", sa.JSON(), nullable=False, server_default="'[]'"),
    sa.Column("responsable_id", UUID, FK→"user".id SET NULL, nullable),
    sa.Column("desde", sa.Date(), nullable=False),
    sa.Column("hasta", sa.Date(), nullable=True),
    sa.Column("created_at", sa.DateTime, server_default=now()),
    sa.Column("updated_at", sa.DateTime, server_default=now()),
    sa.Column("deleted_at", sa.DateTime, nullable=True),
  )
  # Indexes + trigger updated_at en asignacion

downgrade():
  op.drop_table("asignacion")
  # Restaurar email plaintext
  op.add_column("user", sa.Column("email", sa.String(255), nullable=True))
  # [Data migration inversa si es necesario]
  op.drop_constraint("uq_user_tenant_email_hash", "user")
  op.drop_index("idx_user_email_hash", "user")
  op.drop_column("user", "email_hash")
  op.drop_column("user", "email_cifrado")
  op.drop_column("user", "facturador")
  ... [columnas PII en orden inverso] ...
  op.alter_column("user", "apellidos", new_column_name="apellido")
```

**Nota sobre fixtures de tests**: los `conftest.py` existentes (C-02/C-03) crean users con
`email=`. Tras esta migración, el service `create_usuario` recibe `email` plaintext y deriva
internamente `email_cifrado = encrypt(email)` y `email_hash = hmac_email(email)`. Los fixtures
llaman al service, no insertan directo en DB, así que se actualizan solos.

---

## Open Questions para C-07

| ID | Pregunta | Impacto |
|----|----------|---------|
| OQ-C07-1 | ¿El ADMIN puede ver el email de otro tenant por error de scope? | El repo debe filtrar por tenant_id en TODO query de usuario. |
| OQ-C07-2 | ¿Qué pasa si se soft-delete un Usuario con Asignaciones activas? | FK RESTRICT en asignacion.usuario_id impide el borrado físico; soft-delete en user NO borra asignaciones. La lógica de negocio debe desactivar (is_active=False) en lugar de soft-delete si hay asignaciones vigentes. Decisión pendiente: ¿rechazar soft-delete o permitirlo con warning? → **propuesta: rechazar si hay asignaciones vigentes (400)**. |
| OQ-C07-3 | ¿El COORDINADOR puede listar/ver perfiles de usuario completos (con PII) vía asignaciones? | `equipos:asignar` cubre el CRUD de asignaciones. La PII del usuario solo la expone el endpoint de `/admin/usuarios` con `usuarios:gestionar`. En `/asignaciones` la respuesta incluye solo `usuario_id`, no el perfil completo. |
