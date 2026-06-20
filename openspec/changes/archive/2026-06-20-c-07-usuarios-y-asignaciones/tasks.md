## 0. Primitivas criptográficas + TypeDecorator

- [x] 0.1 Agregar `hmac_email(email: str) → str` en `backend/app/core/encryption.py`:
  ```python
  import hmac as _hmac, hashlib
  def hmac_email(email: str) -> str:
      key = settings.ENCRYPTION_KEY.encode("utf-8")
      normalized = email.strip().lower()
      return _hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
  ```
  Esta función es el blind index para el lookup de login (D-C07-2).

- [x] 0.2 Agregar `EncryptedString(TypeDecorator)` en `backend/app/models/base.py`:
  - `impl = String`, `cache_ok = True`
  - `process_bind_param`: llama `encrypt(value)` si `value is not None`
  - `process_result_value`: llama `decrypt(value)` si `value is not None`
  - Importa `encrypt/decrypt` desde `app.core.encryption` (C-02, ya existe)

## 1. Migración 006 (`backend/alembic/versions/c6d7e8f9a0b1_006_usuario_pii_asignacion.py`)

- [x] 1.1 Crear migración manual (NO `--autogenerate`):
  - `revision = "c6d7e8f9a0b1"`, `down_revision = "b5c6d7e8f9a0"`
  - `upgrade()`:
    - `op.alter_column("user", "apellido", new_column_name="apellidos")`
    - ADD `email_cifrado TEXT nullable`, `email_hash VARCHAR(64) nullable`
    - `op.execute("UPDATE ...")` — migración de datos en dev/test: no hay filas reales,
      así que esta sección puede quedar vacía con comentario explicativo
    - `op.alter_column("user", "email_cifrado", nullable=False, server_default="''")`
    - `op.alter_column("user", "email_hash", nullable=False, server_default="''")`
    - `op.drop_column("user", "email")`  ← eliminar plaintext
    - `op.create_unique_constraint("uq_user_tenant_email_hash", "user", ["tenant_id", "email_hash"])`
    - `op.create_index("idx_user_email_hash", "user", ["email_hash"])`
    - ADD PII fields: `dni_cifrado`, `cuil_cifrado`, `cbu_cifrado`, `alias_cbu_cifrado`,
      `banco`, `regional`, `legajo`, `legajo_profesional`, `facturador BOOL NOT NULL DEFAULT false`
    - `op.create_table("asignacion", ...)` con todas las columnas de E5 (ver design.md)
    - Trigger `updated_at` en asignacion
    - Indexes parciales en asignacion: `idx_asignacion_tenant`, `idx_asignacion_usuario`,
      `idx_asignacion_rol`, `idx_asignacion_materia`, `idx_asignacion_cohorte`,
      `idx_asignacion_vigencia` (desde, hasta) — todos `WHERE deleted_at IS NULL`
  - `downgrade()`:
    - DROP TABLE asignacion
    - DROP columnas PII de user en orden inverso
    - Restaurar `email`: ADD `email VARCHAR(255) nullable`
    - DROP `idx_user_email_hash`, constraint `uq_user_tenant_email_hash`
    - DROP `email_hash`, `email_cifrado`
    - `op.alter_column("user", "apellidos", new_column_name="apellido")`
- [x] 1.2 `alembic upgrade head` en `trace_test` y `trace`

## 2. Actualizar modelo `User` (`backend/app/models/user.py`)

- [x] 2.1 Renombrar `apellido` → `apellidos` en el modelo ORM
- [x] 2.2 Reemplazar campo `email: Mapped[str]` por dos campos:
  - `email_cifrado: Mapped[str] = mapped_column(EncryptedString, nullable=False)`
  - `email_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)`
- [x] 2.3 Agregar campos PII con `EncryptedString` TypeDecorator:
  - `dni_cifrado: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)`
  - `cuil_cifrado: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)`
  - `cbu_cifrado: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)`
  - `alias_cbu_cifrado: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)`
- [x] 2.4 Agregar campos de perfil:
  - `banco: Mapped[str | None] = mapped_column(String(255), nullable=True)`
  - `regional: Mapped[str | None] = mapped_column(String(255), nullable=True)`
  - `legajo: Mapped[str | None] = mapped_column(String(100), nullable=True)`
  - `legajo_profesional: Mapped[str | None] = mapped_column(String(100), nullable=True)`
  - `facturador: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")`
- [x] 2.5 Actualizar auth service C-03 (`backend/app/core/auth/service.py`):
  - Login: cambiar `WHERE email == :email` → `WHERE email_hash == hmac_email(:email)`
  - Importar `hmac_email` desde `app.core.encryption`
- [x] 2.6 Actualizar `conftest.py` y fixtures de tests C-02/C-03:
  - El helper `create_user(email=...)` del conftest debe llamar al service (no insertar directo)
  - El service `create_usuario` recibe `email` plaintext y deriva `email_cifrado` + `email_hash`

## 3. Nuevo modelo `Asignacion` (`backend/app/models/asignacion.py`)

- [x] 3.1 Crear `backend/app/models/asignacion.py`:
  - `class Asignacion(Base, BaseEntityMixin)`
  - `usuario_id: Mapped[UUID]` — `ForeignKey("user.id", ondelete="RESTRICT")`, nullable=False
  - `rol_id: Mapped[UUID]` — `ForeignKey("rol.id", ondelete="RESTRICT")`, nullable=False
  - `materia_id: Mapped[UUID | None]` — `ForeignKey("materia.id", ondelete="RESTRICT")`, nullable=True
  - `carrera_id: Mapped[UUID | None]` — `ForeignKey("carrera.id", ondelete="RESTRICT")`, nullable=True
  - `cohorte_id: Mapped[UUID | None]` — `ForeignKey("cohorte.id", ondelete="RESTRICT")`, nullable=True
  - `comisiones: Mapped[list[str]] = mapped_column(sa.JSON(), nullable=False, server_default="'[]'")`
  - `responsable_id: Mapped[UUID | None]` — `ForeignKey("user.id", ondelete="SET NULL")`, nullable=True
  - `desde: Mapped[date] = mapped_column(Date, nullable=False)`
  - `hasta: Mapped[date | None] = mapped_column(Date, nullable=True)`
- [x] 3.2 Actualizar `backend/app/models/__init__.py` — exportar `Asignacion`

## 4. Repositorios

- [x] 4.1 Crear `backend/app/repositories/usuario_repository.py`:
  - `UsuarioRepository(UserRepository)` — extiende `UserRepository` para añadir `has_asignaciones_vigentes()`
  - `get_by_email_hash` heredado de `UserRepository`
  - `has_asignaciones_vigentes(usuario_id) → bool`
- [x] 4.2 Crear `backend/app/repositories/asignacion_repository.py`:
  - `AsignacionRepository(BaseRepository[Asignacion])`
  - `list_vigentes(today: date) → Sequence[Asignacion]`
  - `list_vencidas(today: date) → Sequence[Asignacion]`
- [x] 4.3 Actualizar `backend/app/repositories/__init__.py`

## 5. Schemas Pydantic

### `backend/app/schemas/usuarios.py`

Todos con `model_config = ConfigDict(extra='forbid')`.

- [x] 5.1 `UsuarioCreate`: nombre, apellidos, email: EmailStr, password, PII opcionales, facturador: bool=False
- [x] 5.2 `UsuarioUpdate`: todos opcionales, estado: Literal["Activo","Inactivo"]|None
- [x] 5.3 `UsuarioResponse`: id, tenant_id, nombre, apellidos, email (plaintext via TypeDecorator), PII plaintext, perfil, facturador, estado, timestamps

### `backend/app/schemas/asignaciones.py`

- [x] 5.4 `AsignacionCreate`: usuario_id, rol_id, PK opts, comisiones=[], desde, hasta=None
- [x] 5.5 `AsignacionUpdate`: comisiones, responsable_id, hasta (todos opcionales; usuario_id/rol_id inmutables)
- [x] 5.6 `AsignacionResponse`: todos los campos + `estado_vigencia: str` inyectado por el servicio

## 6. Servicios

### `backend/app/services/usuario_service.py`

- [x] 6.1 `UsuarioService`: create/list/get/update/delete con PII, unicidad email por tenant, bloqueo delete si tiene asignaciones vigentes

### `backend/app/services/asignacion_service.py`

- [x] 6.2 `AsignacionService`: create (valida usuario/rol en tenant, ALUMNO bloqueado, hasta>=desde), list con filtro vigente, get, update, delete; `_vigencia()` puro
- [x] 6.3 Actualizar `backend/app/services/__init__.py`

## 7. Routers

### `backend/app/api/v1/routers/usuarios.py`

- [x] 7.1 5 endpoints bajo `/api/v1/admin`, guard `usuarios:gestionar`, error mapping 404/409/400

### `backend/app/api/v1/routers/asignaciones.py`

- [x] 7.2 5 endpoints bajo `/api/v1`, guard `equipos:asignar`, query `?vigente=bool|None`
- [x] 7.3 Registrar ambos routers en `backend/app/main.py`

## 8. Tests

### `backend/tests/test_usuarios.py`

- [x] 8.1 `TestUsuarioABM` (9 tests): create, dup 409, email otro tenant 201, list, get, cross-tenant 404, update, soft-delete 204→404, sin permiso 403
- [x] 8.2 `TestPIICifrado` (2 tests): DB tiene ciphertext, response tiene plaintext
- [x] 8.2b `TestDeleteConAsignacion` (1 test): 400 cuando hay asignación vigente

### `backend/tests/test_asignaciones.py`

- [x] 8.3 `TestAsignacionABM` (10 tests): create, usuario otro tenant 404, rol ALUMNO 400, hasta<desde 400, list, get, cross-tenant 404, update, soft-delete 204→404, sin permiso 403
- [x] 8.4 `TestVigencia` (7 tests): vigente en rango, vencida hasta pasada, vigente sin hasta, vencida desde futuro, list vigente=true, list vigente=false, estado_vigencia en response

## Fixes incluidos en C-07

- [x] Fix `test_refresh_expired_token` (C-03): asyncpg en Windows interpretaba datetimes naive como hora local (UTC+2); fix: pasar datetime tz-aware al UPDATE. Sin cambios en código de producción.
- [x] Fix `BaseRepository.get_by_id()`: agregado filtro `deleted_at.is_(None)` para que soft-deleted records retornen 404.
- [x] Fix fixtures de aislamiento: añadido `TRUNCATE TABLE asignacion` a 6 fixtures que hacen DELETE FROM rol/user, previniendo FK RESTRICT violations.

## Resultado final

**278 tests passed / 0 failed / 0 errors**
