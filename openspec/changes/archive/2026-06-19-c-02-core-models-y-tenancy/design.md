## Context

activia-trace necesita un modelo de datos antes de poder persistir cualquier entidad de dominio. En C-01 se creó el scaffold: engine async SQLAlchemy 2.0, `Base` declarativa, sesión-por-request vía `get_db`, y config con `ENCRYPTION_KEY` validada. Pero no existe ni una tabla, ni un repositorio, ni un mecanismo de cifrado.

C-02 llena ese vacío con cuatro piezas fundamentales:

1. **Modelo `Tenant`** como raíz del multi-tenancy (ADR-002 row-level).
2. **Mixin base** compuesto que toda entidad del sistema hereda: UUID, tenant_id, timestamps automáticos, soft delete.
3. **Repository genérico** con scope de tenant siempre activo — el contrato de aislamiento (ADR-002).
4. **Utilidad AES-256-GCM** para cifrar PII en reposo (DNI, CUIL, CBU, email) — requisito regulatorio y de diseño (RNF-08).

Estas cuatro piezas son el cimiento de persistencia. Ninguna entidad de dominio (Carrera, Materia, Usuario, etc.) se crea sin este cimiento.

## Goals / Non-Goals

**Goals:**

- Modelo `Tenant` en SQLAlchemy 2.0 async con UUID primary key generado por DB (`gen_random_uuid()`), campos `nombre`, `codigo` (único, interno del sistema), `estado` (activo/inactivo).
- Mixin base `TimeStampedMixin` con `created_at` (server default `now()`) y `updated_at` (auto-actualizado por trigger DB).
- Mixin `SoftDeleteMixin` con `deleted_at` nullable (soft delete).
- Mixin `TenantScopedMixin` que combina los anteriores y agrega `tenant_id` como FK al Tenant.
- El mixin combinado se llama `BaseEntityMixin` y es lo que cada modelo de dominio importa.
- `BaseRepository[ModelT]` genérico con:
  - `list()` → filtra `tenant_id` y `deleted_at IS NULL`
  - `get_by_id(id)` → filtra `tenant_id`
  - `create(data)` → asigna `tenant_id` automáticamente
  - `update(id, data)` → filtra `tenant_id`
  - `soft_delete(id)` → setea `deleted_at` (no borrado físico)
  - `list_with_deleted()` → incluye soft-deleted (solo para auditoría)
  - Sin método `hard_delete` expuesto.
- `core/encryption.py` con AES-256-GCM: `encrypt(plaintext) -> str` y `decrypt(ciphertext) -> str`. El ciphertext incluye nonce + tag + payload codificado en base64.
- Migración Alembic 001: extensión `pgcrypto`, tabla `tenant`, trigger de `updated_at`.
- Tests: modelo tenant, mixin timestamps, soft delete, repository CRUD con scope, cifrado round-trip, **aislamiento multi-tenant** (tenant A no ve datos de tenant B).

**Non-Goals:**

- Modelos de dominio concretos (Carrera, Materia, Usuario, etc.) → C-06+.
- Auth, JWT, Argon2id, 2FA → C-03.
- RBAC, matriz de permisos, `require_permission` → C-04.
- Audit log de negocio (E-AUD) → C-05.
- Integración con Moodle, workers, comunicaciones → changes posteriores.
- Hard delete: expresamente prohibido en este diseño. Si un caso de uso futuro requiere purga física, se diseña como feature explícita con auditoría.

## Decisions

### D1 — Estrategia de mixins: composición, no herencia única

Se usan **tres mixins independientes** que se combinan en un `BaseEntityMixin` para uso común:

```
BaseEntityMixin(TimeStampedMixin, SoftDeleteMixin, TenantScopedMixin)
```

| Mixin | Columnas | Propósito |
|-------|----------|-----------|
| `TimeStampedMixin` | `id: Mapped[UUID]` (PK, default `gen_random_uuid()`), `created_at: Mapped[datetime]` (server_default=`now()`), `updated_at: Mapped[datetime]` (onupdate via trigger) | Timestamps base para toda entidad |
| `SoftDeleteMixin` | `deleted_at: Mapped[Optional[datetime]]` (nullable) | Soft delete transversal |
| `TenantScopedMixin` | `tenant_id: Mapped[UUID]` (FK → `tenant.id`, NOT NULL) + `__tenant_id__` class var para filtro automático | Aislamiento multi-tenant |

`BaseEntityMixin` combina los tres y es lo que usan los modelos de negocio. Si un modelo futuro necesita no tener soft delete o no ser tenant-scoped (p.ej., tablas de sistema o catálogos globales), puede heredar solo los mixins que necesita — aunque en la práctica ADR-002 exige tenant_id en TODA tabla de datos del dominio.

**Alternativa descartada**: un único `Base` con todo incluido. Se descarta porque reduce flexibilidad: tablas de sistema (ej. catálogo de scopes de commit) no deberían tener tenant_id. La composición permite elegir granularidad sin perder el contrato.

**UUID strategy**: se usa `sqlalchemy.text("gen_random_uuid()")` como server default. `gen_random_uuid()` es la función estándar de PostgreSQL desde pgcrypto (y es parte de `pg_catalog` desde PG 13, no requiere extensión explícita en PG 13+). Para compatibilidad, la migración ejecuta `CREATE EXTENSION IF NOT EXISTS pgcrypto`.

### D2 — `updated_at` vía trigger DB, no SQLAlchemy `onupdate`

`updated_at` se actualiza automáticamente mediante un **trigger de PostgreSQL** (función `update_updated_at_column()`), **no** mediante `onupdate=func.now()` de SQLAlchemy. Razones:

- Consistencia: cualquier UPDATE directo a la DB (migrations, scripts de mantenimiento) también actualiza el timestamp.
- Rendimiento: el trigger es por-row, pero es el estándar en PostgreSQL y no hay impacto medible hasta escalas muy superiores a las esperadas.
- El trigger se crea en la migración 001 y se aplica a todas las tablas que usan el mixin (se asocia a la columna `updated_at`).

La función y el trigger se definen en la migración:

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Luego por cada tabla: `CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();`

**Alternativa descartada**: `onupdate=func.now()` de SQLAlchemy. Se descarta porque solo funciona cuando el UPDATE pasa por SQLAlchemy; updates directos o scripts de migración no lo gatillan, lo que rompe la consistencia del timestamp.

### D3 — Repository genérico con tenant_id inyectado en construcción

```python
class BaseRepository[T: BaseEntityMixin]:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None: ...
```

- El `tenant_id` se recibe en el constructor, no por parámetro en cada método — así es imposible olvidar el scope en una llamada individual.
- Todos los queries SELECT/UPDATE/DELETE incluyen `WHERE tenant_id = :tenant_id`.
- El método `create` asigna el `tenant_id` del repositorio al modelo antes de agregarlo a la sesión.
- El método `soft_delete` setea `deleted_at` y hace flush.
- NO existe `hard_delete`. Si un caso de uso futuro requiere purga física, se crea una subclase `HardDeleteRepository` o un método explícito con nombre `purge_physical` y se revisa en code review.
- `list_with_deleted(id)` omite el filtro `deleted_at IS NULL` pero **nunca** omite el filtro de tenant_id.

```python
class BaseRepository[T: BaseEntityMixin]:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._model_class: type[T] = ...  # set by subclass or generic

    async def list(self) -> Sequence[T]:
        stmt = select(self._model_class).where(
            self._model_class.tenant_id == self._tenant_id,
            self._model_class.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, id: UUID) -> T | None:
        stmt = select(self._model_class).where(
            self._model_class.id == id,
            self._model_class.tenant_id == self._tenant_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: T | dict) -> T:
        if isinstance(data, dict):
            model = self._model_class(**data, tenant_id=self._tenant_id)
        else:
            model = data
            model.tenant_id = self._tenant_id
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(self, id: UUID, data: dict) -> T | None:
        model = await self.get_by_id(id)
        if model is None:
            return None
        for key, value in data.items():
            setattr(model, key, value)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def soft_delete(self, id: UUID) -> bool:
        model = await self.get_by_id(id)
        if model is None:
            return False
        model.deleted_at = func.now()
        await self._session.flush()
        return True

    async def list_with_deleted(self) -> Sequence[T]:
        stmt = select(self._model_class).where(
            self._model_class.tenant_id == self._tenant_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
```

**Alternativa descartada**: pasar `tenant_id` en cada llamado del método. Riesgo alto de omitir el filtro en alguna llamada — el diseño lo previene inyectándolo en el constructor. Tampoco se usa contextvar de tenant (request-scoped implícito) porque la sesión async no garantiza aislamiento de contextvars entre corutinas concurrentes.

### D4 — AES-256-GCM con nonce almacenado inline

```
ciphertext_b64 = base64(nonce (12 bytes) + ciphertext + tag (16 bytes))
```

- Algoritmo: **AES-256-GCM** (authenticated encryption).
- Clave: `ENCRYPTION_KEY` de settings (exactamente 32 bytes / 32 chars UTF-8 → se convierte a bytes con `.encode("utf-8")`).
- Nonce: 12 bytes aleatorios por cifrado (`os.urandom(12)`).
- Tag GCM: 16 bytes (autenticación).
- Output: un único string base64 (URL-safe, sin padding) que contiene nonce + ciphertext + tag concatenados.
- No se usa storage separado para el nonce: va inline en el ciphertext.
- El módulo `core/encryption.py` expone:
  - `encrypt(plaintext: str) -> str`
  - `decrypt(ciphertext: str) -> str`
- Tipado: los datos cifrados se almacenan en columnas TEXT de PostgreSQL.
- NUNCA se loguea el valor original ni el ciphertext completo (solo metadatos: "campo X cifrado OK").
- Si la clave es inválida o el ciphertext está corrupto, las funciones lanzan excepción (`ValueError` o `cryptography.InvalidTag`).

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt(plaintext: str) -> str:
    key = settings.ENCRYPTION_KEY.encode("utf-8")
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")

def decrypt(ciphertext_b64: str) -> str:
    key = settings.ENCRYPTION_KEY.encode("utf-8")
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(ciphertext_b64)
    nonce = raw[:12]
    ciphertext = raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
```

**Dependencia**: `cryptography` (librería estándar para operaciones criptográficas en Python). Se agrega a `pyproject.toml`.

**Alternativa descartada**: AES-256-CBC con HMAC separado. Se descarta porque GCM provee authenticated encryption en una sola operación, evitando la complejidad de gestionar IV + ciphertext + MAC por separado y los riesgos de padding oracle en CBC. AES-256-GCM es la recomendación NIST para nuevos sistemas.

### D5 — Migración Alembic 001

La primera migración:

1. Crea extensión `pgcrypto` (para `gen_random_uuid()` si no existe en PG <13).
2. Crea la función trigger `update_updated_at_column()`.
3. Crea la tabla `tenant` con:
   - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
   - `nombre VARCHAR NOT NULL`
   - `codigo VARCHAR NOT NULL UNIQUE`
   - `estado VARCHAR NOT NULL DEFAULT 'activo'` (check: activo/inactivo)
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `deleted_at TIMESTAMPTZ`
4. Crea trigger `trg_tenant_updated_at` en tabla `tenant`.

Convención: una migración Alembic por cambio de schema. La migración 001 es exclusivamente para el modelo Tenant. Las migraciones siguientes (002, 003...) corresponden a cambios de schema de otros models.

### D6 — Tests con base de datos real (sin mocks)

Siguiendo la regla dura #4 del proyecto (sin mocks de DB), los tests de C-02 usan una base de datos PostgreSQL real (`DATABASE_URL_TEST` de conftest.py ya configurado en C-01).

- `conftest.py` recibe fixtures:
  - `db_session`: sesión async limpia por test (ya existe en C-01).
  - `create_tenant(db_session, codigo, nombre)`: crea un tenant y hace commit.
  - `another_tenant`: crea un segundo tenant para tests de aislamiento.
- Tests planificados:
  - `test_tenant_model.py`: crear tenant, leer por id, verificar UUID generado, verificar timestamps.
  - `test_base_mixin.py`: crear un modelo dummy que herede `BaseEntityMixin`, verificar que `id`, `created_at`, `updated_at`, `tenant_id`, `deleted_at` existen y funcionan.
  - `test_base_repository.py`: CRUD completo, soft delete, `list_with_deleted`, aislamiento (tenant A no ve datos de B), `get_by_id` de otro tenant retorna None, `update`, `soft_delete` de inexistente retorna False.
  - `test_encryption.py`: round-trip encrypt → decrypt, texto vacío, caracteres UTF-8 (ñ, acentos), datos binarios, clave incorrecta lanza error, ciphertext corrupto lanza error.

**Test de aislamiento multi-tenant (crítico)**:

```python
async def test_tenant_isolation(db_session, create_tenant, another_tenant):
    tenant_a = await create_tenant("TENANT_A")
    tenant_b = await create_tenant("TENANT_B")
    repo_a = TenantRepository(db_session, tenant_a.id)
    repo_b = TenantRepository(db_session, tenant_b.id)
    
    # Crear un tenant (para este test, usamos tenant como modelo de prueba)
    # Verificar que repo_a list() NO incluya datos de repo_b
    # y viceversa
    ...
```

### D7 — No hay hard delete expuesto

El `BaseRepository` no tiene método `hard_delete` ni `delete`. La única operación de borrado es `soft_delete`, que setea `deleted_at`. Esto es deliberado: el proyecto exige soft delete siempre (regla dura #13) y auditoría append-only. Si un caso de uso futuro requiere purga física, se diseña explícitamente como feature separada.

## Risks / Trade-offs

- **[Trigger DB para updated_at agrega lógica en la base de datos]** → Mitigación: es el estándar PostgreSQL, bien entendido, y centraliza la responsabilidad del timestamp. El trigger se crea en la migración 001 y es transparente para el código Python.
- **[AES-256-GCM nonce inline aumenta el tamaño del ciphertext]** → Mitigación: el overhead es de 28 bytes (12 nonce + 16 tag) más base64 encoding (~33% del ciphertext). Para campos de longitud acotada (DNI 8 chars, CUIL 11 chars, email ∼50 chars), el overhead es irrelevante (< 200 chars total).
- **[Dependencia cryptography nueva]** → Mitigación: `cryptography` es la librería criptográfica estándar de facto en Python, mantenida por PyCA, with wheels para todas las plataformas. No introduce riesgo de mantenimiento.
- **[Repository genérico con generic type variable requiere Python 3.12+]** → Mitigación: el proyecto usa Python 3.13. La sintaxis `[T: BaseEntityMixin]` (PEP 695) está disponible.
- **[gen_random_uuid() no requiere extensión pgcrypto en PG 13+]** → Mitigación: la migración ejecuta `CREATE EXTENSION IF NOT EXISTS pgcrypto` que es idempotente. Si ya existe (PG 13+ lo incluye en `pg_catalog`), no falla.
- **[Un query sin scope de tenant podría colarse si alguien no usa BaseRepository]** → Mitigación: todos los queries del dominio DEBEN pasar por repositories. El contrato de arquitectura (Routers → Services → Repositories → Models) lo exige. Code review debe verificar que ningún repository omite el filtro. El `BaseRepository` hace imposible omitirlo por accidente.

## Migration Plan

No hay migración de datos (primer schema). Deploy:
1. Ejecutar `alembic upgrade head` → crea extensión pgcrypto, trigger y tabla tenant.
2. El seed de un tenant inicial (TUPAD) se hará en C-03 o manualmente para desarrollo.
3. Rollback: `alembic downgrade -1` revierte la migración 001 (dropea tabla tenant, trigger y extensión si no hay dependientes).

## Open Questions

- **Seed inicial de tenant**: ¿El tenant "TUPAD" se crea mediante un script de seed (C-02) o en C-03 (auth) cuando se necesita el primer usuario admin? Se decide en apply: recomiendo agregar un script `scripts/seed_dev.py` en C-02 para que el entorno de desarrollo sea funcional inmediatamente.
- **Método `count` en BaseRepository**: ¿necesario ahora o se agrega cuando se necesite? Se omite por ahora (YAGNI) — se agrega en el change que lo requiera.
- **¿Usar UUID como string (VARCHAR) o como tipo UUID de PostgreSQL?**: Se usa `sqlalchemy.UUID(as_uuid=True)` que mapea al tipo nativo `uuid` de PostgreSQL. El tipo nativo es más eficiente (16 bytes vs 32+ bytes como string). Todos los modelos reciben/emiten objetos `uuid.UUID` de Python.
