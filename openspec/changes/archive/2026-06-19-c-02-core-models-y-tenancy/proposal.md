## Why

activia-trace no tiene modelo de datos ni mecanismo de aislamiento multi-tenant. Sin un modelo `Tenant` raíz, un mixin base común para todas las entidades (UUID, timestamps, soft delete, tenant_id), un repository genérico que garantice el scope de tenant en cada consulta (ADR-002 row-level), y una utilidad de cifrado AES-256 para atributos sensibles, ningún change posterior (C-03 auth, C-04 RBAC, C-06 estructura académica) puede escribir modelos de dominio ni persistir datos. Este change sienta las bases de persistencia sobre las que se construye todo el sistema.

## What Changes

- **Modelo `Tenant` raíz**: tabla `tenant` con campos `id` (UUID), `nombre`, `codigo` (único interno, ej. "tupad"), `estado` (activo/inactivo), y los campos del mixin base.
- **Mixin base `TimeStampedMixin` + `SoftDeleteMixin`**: cada modelo hereda `id` (UUID PK default `uuid_generate_v4()` SQL-side), `tenant_id` (FK → Tenant), `created_at`, `updated_at` (manejados automáticamente por la DB), `deleted_at` (nullable, soft delete).
- **Mixin `TenantScopedMixin`**: combina los anteriores y agrega `__tenant_id__` para que los repositorios puedan filtrar automáticamente.
- **Repository genérico `BaseRepository`**: clase base que recibe el modelo y el `tenant_id`, y wrappea operaciones CRUD con filtro de tenant siempre activo. Incluye: `list`, `get_by_id`, `create`, `update`, `soft_delete` (setea `deleted_at`), `hard_delete` **prohibido por defecto**.
- **Utilidad AES-256 `encryption.py`**: helpers para cifrar/descifrar con AES-256-GCM usando `ENCRYPTION_KEY` de settings. Métodos `encrypt(plaintext: str) -> str` y `decrypt(ciphertext: str) -> str` que devuelven strings seguros para almacenar en columna TEXT. Implementa authenticated encryption con nonce aleatorio.
- **Migración Alembic 001**: crea extensión `pgcrypto` (uuid-ossp en desuso, se usa `gen_random_uuid()`), tabla `tenant`, y función trigger para `updated_at`.
- **Convención de soft delete**: el repository **nunca** expone hard delete. La única forma de "borrar" un registro es setear `deleted_at`. Los queries `list` filtran `WHERE deleted_at IS NULL` por defecto; existe método `list_with_deleted` para auditoría.
- **Aislamiento multi-tenant**: todos los queries del `BaseRepository` incluyen `WHERE tenant_id = :tenant_id`. No hay forma de omitir el filtro sin crear un método ad-hoc explícito para cross-tenant queries (que deben ser revisados explícitamente).
- **Tests**: suite completa con base de datos real: creación de tenant, mixin timestamps, soft delete (crear → soft_delete → list no lo trae → list_with_deleted lo trae), cifrado round-trip, y **test de aislamiento**: datos creados con tenant_id=A no son visibles desde queries con tenant_id=B.

**No hay cambios BREAKING**: es el segundo change del proyecto, solo models/encryption/repository se agregan sobre el scaffold de C-01.

## Capabilities

### New Capabilities

- `tenant-model`: Entidad Tenant como raíz del multi-tenancy. Creación, activación/desactivación, validación de unicidad de `codigo` por tenant.
- `base-entity-mixin`: Mixin base ORM que toda entidad del dominio hereda: `id` (UUID), `tenant_id` (FK → Tenant), `created_at`, `updated_at`, `deleted_at`. Provee el contrato de soft delete y timestamps automáticos.
- `tenant-scoped-repository`: Repository genérico `BaseRepository[ModelT]` que implementa CRUD con scope de tenant siempre activo. Métodos: `list`, `get_by_id`, `create`, `update`, `soft_delete`, `list_with_deleted`. Sin hard delete expuesto.
- `aes-256-pii-encryption`: Utilidad de cifrado AES-256-GCM en reposo para atributos PII marcados como `[cifrado]` (DNI, CUIL, CBU, email). Funciones `encrypt`/`decrypt` con nonce aleatorio y authenticated encryption.
- `alembic-migration-001`: Primera migración Alembic que crea la tabla `tenant` con todas sus columnas más la extensión `pgcrypto`/`gen_random_uuid()` y el trigger de `updated_at`.

### Modified Capabilities

<!-- Ninguna: es el segundo cambio del proyecto, no existen specs previos que modificar. El reservado core/security.py en C-01 recibe la utilidad AES-256, pero eso es implementación (no cambia requirements de spec previo). -->

## Impact

- **Nuevo código**: `app/core/encryption.py` (AES-256-GCM helper), `app/models/tenant.py` (modelo Tenant), `app/models/base.py` (mixins TimeStampedMixin + SoftDeleteMixin + TenantScopedMixin), `app/repositories/base.py` (BaseRepository genérico con scope de tenant), `app/repositories/__init__.py` (actualizado), `app/models/__init__.py` (actualizado).
- **Archivos modificados**: `app/core/security.py` (recibe la utilidad de cifrado o referencia a encryption.py), `alembic/versions/` (nueva migración 001), `backend/tests/conftest.py` (nuevas fixtures: `test_db_url`, `create_tenant`, `another_tenant`).
- **Nuevos tests**: `tests/test_tenant_model.py`, `tests/test_base_mixin.py`, `tests/test_base_repository.py`, `tests/test_encryption.py`.
- **No hay nuevas dependencias**: AES-256 usa `cryptography` (ya en el stack implícito) o la stdlib `hashlib`+`os.urandom`. Si `cryptography` no está en `pyproject.toml`, se agrega.
- **Dependencias**: requiere C-01 (scaffold, database.py, config.py con `ENCRYPTION_KEY` validada).
- **Habilita** a C-03 (auth) y C-04 (RBAC) y a todos los changes de Fase 2 en adelante que necesiten persistir modelos de dominio.
- **Governance**: CRITICO — modelo de datos core, multi-tenancy, cifrado de PII, soft delete. Errores aquí comprometen la seguridad y el aislamiento de todo el sistema.
