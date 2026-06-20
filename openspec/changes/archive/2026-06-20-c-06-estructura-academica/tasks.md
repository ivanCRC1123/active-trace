## 0. EstadoBasico enum

- [x] 0.1 Agregar `EstadoBasico(str, enum.Enum)` con `Activa` / `Inactiva` a `backend/app/models/base.py` (junto a `BaseEntityMixin`)

## 1. Modelo Carrera

- [x] 1.1 Crear `backend/app/models/carrera.py`:
  - Hereda `BaseEntityMixin` (id, tenant_id, created_at, updated_at, deleted_at)
  - `codigo: Mapped[str]` — `String(50)`, nullable=False, index=True
  - `nombre: Mapped[str]` — `String(255)`, nullable=False
  - `estado: Mapped[EstadoBasico]` — `sa.Enum(EstadoBasico, name="estado_basico", create_type=False)`, nullable=False, server_default="Activa"
  - `__table_args__`: `UniqueConstraint("tenant_id", "codigo", name="uq_carrera_tenant_codigo")`
- [x] 1.2 Actualizar `backend/app/models/__init__.py` — exportar `Carrera`

## 2. Modelo Cohorte

- [x] 2.1 Crear `backend/app/models/cohorte.py`:
  - Hereda `BaseEntityMixin`
  - `carrera_id: Mapped[UUID]` — `ForeignKey("carrera.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `nombre: Mapped[str]` — `String(100)`, nullable=False
  - `anio: Mapped[int]` — `Integer`, nullable=False
  - `vig_desde: Mapped[date]` — `Date`, nullable=False
  - `vig_hasta: Mapped[date | None]` — `Date`, nullable=True
  - `estado: Mapped[EstadoBasico]` — Enum(EstadoBasico, create_type=False), nullable=False, server_default="Activa"
  - `__table_args__`: `UniqueConstraint("tenant_id", "carrera_id", "nombre", name="uq_cohorte_tenant_carrera_nombre")`
- [x] 2.2 Actualizar `backend/app/models/__init__.py` — exportar `Cohorte`

## 3. Modelo Materia

- [x] 3.1 Crear `backend/app/models/materia.py`:
  - Hereda `BaseEntityMixin`
  - `codigo: Mapped[str]` — `String(50)`, nullable=False, index=True
  - `nombre: Mapped[str]` — `String(255)`, nullable=False
  - `estado: Mapped[EstadoBasico]` — Enum(EstadoBasico, create_type=False), nullable=False, server_default="Activa"
  - `__table_args__`: `UniqueConstraint("tenant_id", "codigo", name="uq_materia_tenant_codigo")`
- [x] 3.2 Actualizar `backend/app/models/__init__.py` — exportar `Materia`

## 4. Migración 005

- [x] 4.1 Crear `backend/alembic/versions/[rev]_005_carrera_cohorte_materia.py` (escribir a mano, NO `--autogenerate`):
  - `revision`: nuevo UUID hex
  - `down_revision = "c05af7b8d9e1"`
  - `upgrade()`:
    1. `sa.Enum(EstadoBasico, name='estado_basico').create(op.get_bind(), checkfirst=True)`
    2. `op.create_table("carrera", ...)` — columnas BaseEntityMixin + codigo, nombre, estado; PK; FK tenant→tenant.id CASCADE; UniqueConstraint
    3. `op.create_table("cohorte", ...)` — columnas + carrera_id FK RESTRICT; UniqueConstraint
    4. `op.create_table("materia", ...)` — columnas + codigo, nombre, estado; UniqueConstraint
    5. Indexes: `idx_carrera_tenant`, `idx_cohorte_tenant`, `idx_cohorte_carrera`, `idx_materia_tenant`, `idx_carrera_estado`, `idx_materia_estado`
  - `downgrade()`:
    1. drop indexes
    2. `op.drop_table("materia")`, `op.drop_table("cohorte")`, `op.drop_table("carrera")`
    3. `sa.Enum(name='estado_basico').drop(op.get_bind(), checkfirst=True)`
- [x] 4.2 Verificar `alembic upgrade head` en `trace_test` y `trace`
- [x] 4.3 Verificar round-trip: `alembic downgrade -1` → `alembic upgrade head`

## 5. Repositorios

- [x] 5.1 Crear `backend/app/repositories/carrera_repository.py`:
  - `CarreraRepository(BaseRepository[Carrera])`
  - `model_class` property → `Carrera`
  - `async def get_by_codigo(self, codigo: str) -> Carrera | None` — filtra por tenant_id + codigo + deleted_at.is_(None)
- [x] 5.2 Crear `backend/app/repositories/cohorte_repository.py`:
  - `CohorteRepository(BaseRepository[Cohorte])`
  - `async def get_by_nombre_carrera(self, nombre: str, carrera_id: UUID) -> Cohorte | None`
  - `async def list_by_carrera(self, carrera_id: UUID) -> list[Cohorte]`
- [x] 5.3 Crear `backend/app/repositories/materia_repository.py`:
  - `MateriaRepository(BaseRepository[Materia])`
  - `async def get_by_codigo(self, codigo: str) -> Materia | None`
- [x] 5.4 Actualizar `backend/app/repositories/__init__.py` — exportar los 3 nuevos repos

## 6. Schemas Pydantic (`backend/app/schemas/estructura_academica.py`)

Todos con `model_config = ConfigDict(extra='forbid')`.

- [x] 6.1 `CarreraCreate`: `codigo: str`, `nombre: str`
- [x] 6.2 `CarreraUpdate`: `codigo: str | None = None`, `nombre: str | None = None`, `estado: EstadoBasico | None = None`
- [x] 6.3 `CarreraResponse`: `id: UUID`, `tenant_id: UUID`, `codigo: str`, `nombre: str`, `estado: EstadoBasico`, `created_at: datetime`, `updated_at: datetime` — `model_config` con `from_attributes=True`
- [x] 6.4 `CohorteCreate`: `carrera_id: UUID`, `nombre: str`, `anio: int`, `vig_desde: date`, `vig_hasta: date | None = None`
- [x] 6.5 `CohorteUpdate`: todos campos opcionales (`nombre?`, `anio?`, `vig_desde?`, `vig_hasta?`, `estado?`)
- [x] 6.6 `CohorteResponse`: `id`, `tenant_id`, `carrera_id`, `nombre`, `anio`, `vig_desde`, `vig_hasta`, `estado`, `created_at`, `updated_at`
- [x] 6.7 `MateriaCreate`: `codigo: str`, `nombre: str`
- [x] 6.8 `MateriaUpdate`: `codigo?`, `nombre?`, `estado?`
- [x] 6.9 `MateriaResponse`: `id`, `tenant_id`, `codigo`, `nombre`, `estado`, `created_at`, `updated_at`

## 7. Service (`backend/app/services/estructura_academica_service.py`)

- [x] 7.1 `EstructuraAcademicaService(session: AsyncSession)`:

  **Carrera:**
  - `create_carrera(*, tenant_id: UUID, data: CarreraCreate) → Carrera`
    - `CarreraRepository.get_by_codigo(data.codigo)` → lanza `ValueError("codigo ya existe")` si existe
    - `repo.create({...data, tenant_id})`
  - `update_carrera(*, id: UUID, tenant_id: UUID, data: CarreraUpdate) → Carrera`
    - `repo.get_by_id(id)` → None → `ValueError("not found")`
    - Si cambia codigo: validar unicidad
    - `repo.update(id, data_dict)` (excluye None)
  - `delete_carrera(*, id: UUID, tenant_id: UUID) → bool`
    - `repo.soft_delete(id)` → False → `ValueError("not found")`

  **Cohorte:**
  - `create_cohorte(*, tenant_id: UUID, data: CohorteCreate) → Cohorte`
    - `CarreraRepository.get_by_id(data.carrera_id)` → None → `ValueError("carrera not found")`
    - `carrera.estado != Activa` → `ValueError("carrera inactiva")`
    - Unicidad `(tenant_id, carrera_id, nombre)` → `ValueError("nombre ya existe")`
    - `repo.create({...data, tenant_id})`
  - `update_cohorte(*, id, tenant_id, data) → Cohorte`
  - `delete_cohorte(*, id, tenant_id) → bool`

  **Materia:**
  - `create_materia(*, tenant_id: UUID, data: MateriaCreate) → Materia`
    - Unicidad `(tenant_id, codigo)` → `ValueError("codigo ya existe")`
    - `repo.create({...data, tenant_id})`
  - `update_materia(*, id, tenant_id, data) → Materia`
  - `delete_materia(*, id, tenant_id) → bool`

- [x] 7.2 Actualizar `backend/app/services/__init__.py`

## 8. Router (`backend/app/api/v1/routers/estructura_academica.py`)

- [x] 8.1 `router = APIRouter(prefix="/api/v1/admin", tags=["estructura-academica"])`

  Todos los endpoints: `_ = Depends(require_permission("estructura_academica:gestionar"))`, extraen `current_user, _scope = _`.

  Errores del servicio mapeados: `ValueError("not found")` → 404; `ValueError("...ya existe"/"nombre ya existe")` → 409; `ValueError("carrera inactiva")` → 400; `ValueError("carrera not found")` → 404.

  ```
  Carreras:
  GET    /carreras           → list[CarreraResponse]
  POST   /carreras           → CarreraResponse, status_code=201
  GET    /carreras/{id}      → CarreraResponse
  PATCH  /carreras/{id}      → CarreraResponse
  DELETE /carreras/{id}      → Response(status_code=204)

  Cohortes:
  GET    /cohortes           → list[CohorteResponse]  (query: carrera_id: UUID | None = None)
  POST   /cohortes           → CohorteResponse, status_code=201
  GET    /cohortes/{id}      → CohorteResponse
  PATCH  /cohortes/{id}      → CohorteResponse
  DELETE /cohortes/{id}      → Response(status_code=204)

  Materias:
  GET    /materias           → list[MateriaResponse]
  POST   /materias           → MateriaResponse, status_code=201
  GET    /materias/{id}      → MateriaResponse
  PATCH  /materias/{id}      → MateriaResponse
  DELETE /materias/{id}      → Response(status_code=204)
  ```

- [x] 8.2 Registrar en `backend/app/main.py`:
  ```python
  from app.api.v1.routers import auth, auditoria, estructura_academica, health
  app.include_router(estructura_academica.router)
  ```

## 9. Tests (`backend/tests/test_estructura_academica.py`)

Usar fixtures `async_client`, `seeded_db` (o fixture equivalente que provea 2 tenants con admin en cada uno).

- [x] 9.1 `TestCarreraABM` (~9 tests):
  - `test_create_carrera_ok` — POST → 201, `codigo` y `nombre` correctos, `estado=Activa`
  - `test_create_carrera_codigo_duplicado_returns_409` — mismo tenant, mismo codigo → 409
  - `test_create_carrera_codigo_duplicado_otro_tenant_ok` — mismo codigo en tenant distinto → 201 (aislamiento)
  - `test_list_carreras_solo_propio_tenant` — lista solo devuelve registros del tenant del actor
  - `test_get_carrera_ok` — GET /{id} → 200 con datos correctos
  - `test_get_carrera_otro_tenant_returns_404` — id de otro tenant → 404
  - `test_update_carrera_ok` — PATCH → 200 con campos actualizados
  - `test_soft_delete_carrera_ok` — DELETE → 204; GET /{id} → 404; sigue en DB con deleted_at
  - `test_no_admin_returns_403` — PROFESOR llama POST → 403

- [x] 9.2 `TestCohorteABM` (~8 tests):
  - `test_create_cohorte_ok` — POST con carrera activa → 201
  - `test_create_cohorte_carrera_inactiva_returns_400` — carrera con estado=Inactiva → 400
  - `test_create_cohorte_carrera_otro_tenant_returns_404` — carrera_id de otro tenant → 404
  - `test_create_cohorte_nombre_duplicado_returns_409` — mismo (tenant, carrera, nombre) → 409
  - `test_list_cohortes_ok` — GET → 200 con resultados del tenant
  - `test_update_cohorte_ok` — PATCH → 200
  - `test_soft_delete_cohorte_ok` — DELETE → 204
  - `test_no_admin_returns_403` — PROFESOR → 403

- [x] 9.3 `TestMateriaABM` (~8 tests):
  - `test_create_materia_ok` — POST → 201
  - `test_create_materia_codigo_duplicado_returns_409`
  - `test_create_materia_codigo_duplicado_otro_tenant_ok` — aislamiento multi-tenant
  - `test_list_materias_ok` — GET → 200
  - `test_get_materia_ok`
  - `test_update_materia_ok`
  - `test_soft_delete_materia_ok`
  - `test_no_admin_returns_403`

- [x] 9.4 `TestEstadoYVigencia` (~4 tests):
  - `test_carrera_inactiva_bloquea_cohorte` — crear cohorte con carrera inactiva → 400
  - `test_reactivar_carrera_permite_cohorte` — PATCH carrera a Activa → crear cohorte → 201
  - `test_materia_inactiva_aparece_en_list` — soft-delete es por deleted_at, estado Inactiva NO oculta el registro
  - `test_cohorte_sin_vig_hasta_abierta_ok` — `vig_hasta=null` → 201 válido
