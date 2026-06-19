## 1. AES-256 encryption utility (`core/encryption.py`)

- [x] 1.1 (RED) Escribir `tests/test_encryption.py`: test de round-trip `encrypt` → `decrypt` recupera el texto original; dos cifrados del mismo texto producen distintos ciphertexts (nonce aleatorio)
- [x] 1.2 (GREEN) Implementar `core/encryption.py` con `encrypt(plaintext: str) -> str` y `decrypt(ciphertext: str) -> str` usando AES-256-GCM (librería `cryptography`). Nonce de 12 bytes aleatorio inline con ciphertext + tag. Output en base64 URL-safe sin padding.
- [x] 1.3 (TRIANGULATE) Agregar casos: texto vacío, UTF-8 con ñ y acentos, clave incorrecta lanza `InvalidTag`, ciphertext corrupto lanza error, y verificar que no se loguea el plaintext ni el ciphertext completo

## 2. Base mixins ORM (`models/base.py`)

- [x] 2.1 (RED) Escribir `tests/test_base_mixin.py`: crear un modelo dummy `_TestModel(BaseEntityMixin)` con columnas extra, verificar que `id` (UUID), `created_at`, `updated_at`, `tenant_id` (FK), `deleted_at` existen y son del tipo correcto; verificar que `id` se auto-genera al insertar; verificar que `created_at` y `updated_at` se setean al crear
- [x] 2.2 (GREEN) Implementar `models/base.py` con los tres mixins:
  - `TimeStampedMixin`: `id` (UUID PK, server_default=`gen_random_uuid()`), `created_at` (TIMESTAMPTZ, server_default=now()), `updated_at` (TIMESTAMPTZ, server_default=now(), onupdate via trigger)
  - `SoftDeleteMixin`: `deleted_at` (TIMESTAMPTZ, nullable, default=None)
  - `TenantScopedMixin`: `tenant_id` (UUID, FK → tenant.id, NOT NULL) + `__tenant_id__` class variable
  - `BaseEntityMixin`: combina los tres mixins
- [x] 2.3 (TRIANGULATE) Verificar que `updated_at` se actualiza al modificar el registro (crear trigger de prueba, modificar, refresh y verificar cambio); verificar que soft delete seteó `deleted_at` no nulo; verificar que `tenant_id` no nulo es requerido

## 3. Modelo Tenant (`models/tenant.py`)

- [x] 3.1 (RED) Escribir `tests/test_tenant_model.py`: crear un tenant con `codigo` y `nombre`, verificar UUID generado, `created_at`/`updated_at` timestamps no nulos, `deleted_at` nulo, `estado` default `"activo"`, violación de unicidad de `codigo`
- [x] 3.2 (GREEN) Implementar `models/tenant.py`: `Tenant` model que hereda `BaseEntityMixin` con columnas `nombre` (VARCHAR NOT NULL), `codigo` (VARCHAR NOT NULL UNIQUE), `estado` (VARCHAR NOT NULL DEFAULT 'activo')
- [x] 3.3 (TRIANGULATE) Agregar casos: soft delete de tenant, listar tenants activos vs. eliminados

## 4. Repository genérico con scope de tenant (`repositories/base.py`)

- [x] 4.1 (RED) Escribir `tests/test_base_repository.py`: instanciar `BaseRepository[Tenant]` con session + tenant_id; testear `create` asigna tenant_id automáticamente; `list` retorna solo activos del tenant; `get_by_id` funciona solo si pertenece al tenant; `update` modifica y retorna; `soft_delete` setea `deleted_at` y excluye de `list`; `list_with_deleted` lo incluye; `soft_delete` de inexistente retorna `False`
- [x] 4.2 (GREEN) Implementar `repositories/base.py` con `BaseRepository[T: BaseEntityMixin]` que recibe `session: AsyncSession` y `tenant_id: UUID` en el constructor. Implementar: `list()`, `get_by_id(id)`, `create(data)`, `update(id, data)`, `soft_delete(id)`, `list_with_deleted()`. Sin método `hard_delete`. Todos los queries filtran por `tenant_id = self._tenant_id`.
- [x] 4.3 (TRIANGULATE) Agregar test de **aislamiento multi-tenant** (crítico): crear dos tenants, insertar datos en cada uno, verificar que `list()` de tenant A no incluye datos de tenant B y viceversa; verificar que `get_by_id()` de un registro de tenant B desde repositorio de tenant A retorna `None`

## 5. Migración Alembic 001 (tenant table)

- [x] 5.1 Crear migración Alembic 001: `alembic revision --autogenerate -m "001_create_tenant"` (o manual si autogenerate no detecta bien los mixins). Revisar que incluya: `CREATE EXTENSION IF NOT EXISTS pgcrypto`, función trigger `update_updated_at_column()`, tabla `tenant`, trigger `trg_tenant_updated_at`, índices necesarios (índice en `tenant_id`, índice único en `codigo`)
- [x] 5.2 Revisar y limpiar la migración autogenerada: asegurar que el upgrade crea solo lo necesario y el downgrade dropea tabla + función trigger (sin dropear pgcrypto)
- [x] 5.3 Ejecutar `alembic upgrade head` contra la base de datos de desarrollo y verificar que la tabla `tenant` se crea correctamente con todas sus columnas y constraints
- [x] 5.4 Ejecutar `alembic downgrade -1` y verificar que la tabla se dropea limpiamente; luego volver a `alembic upgrade head`

## 6. Tests de integración y verificación final

- [x] 6.1 Agregar a `conftest.py` fixtures: `create_tenant(db_session, codigo, nombre)` que crea y commitea un tenant, `another_tenant()` que crea un segundo tenant para tests de aislamiento
- [x] 6.2 Ejecutar suite completa de tests: `pytest -v` y confirmar verde — cifrado round-trip, mixin timestamps, soft delete CRUD, aislamiento multi-tenant, migración
- [x] 6.3 Verificar límite de 500 LOC por archivo: todos los archivos nuevos del change (`encryption.py`, `base.py` de models, `tenant.py`, `base.py` de repositories) deben estar por debajo de 500 líneas
- [x] 6.4 Verificar que no existe hard delete expuesto en ningún método público de `BaseRepository`
- [x] 6.5 Verificar que ningún log contiene PII en claro (revisar `core/encryption.py`)
