## 0. TipoEvaluacion enum

- [x] 0.1 Agregar `TipoEvaluacion(str, enum.Enum)` con `Parcial / TP / Coloquio / Recuperatorio` a `backend/app/models/base.py` (junto a `EstadoBasico`)

## 1. Modelo ProgramaMateria

- [x] 1.1 Crear `backend/app/models/programa_materia.py`:
  - Hereda `BaseEntityMixin` (id, tenant_id, created_at, updated_at, deleted_at)
  - `materia_id: Mapped[UUID]` — `ForeignKey("materia.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `carrera_id: Mapped[UUID]` — `ForeignKey("carrera.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `cohorte_id: Mapped[UUID]` — `ForeignKey("cohorte.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `titulo: Mapped[str]` — `String(255)`, nullable=False
  - `referencia_archivo: Mapped[str]` — `Text`, nullable=False
  - `cargado_at: Mapped[datetime]` — `DateTime(timezone=True)`, server_default=`now()`, nullable=False
  - `__table_args__`: `UniqueConstraint("tenant_id", "materia_id", "carrera_id", "cohorte_id", name="uq_programa_materia_tenant_materia_carrera_cohorte")`
- [x] 1.2 Actualizar `backend/app/models/__init__.py` — exportar `ProgramaMateria`

## 2. Modelo FechaAcademica

- [x] 2.1 Crear `backend/app/models/fecha_academica.py`:
  - Hereda `BaseEntityMixin`
  - `materia_id: Mapped[UUID]` — `ForeignKey("materia.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `cohorte_id: Mapped[UUID]` — `ForeignKey("cohorte.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `tipo: Mapped[TipoEvaluacion]` — `sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False)`, nullable=False
  - `numero: Mapped[int]` — `Integer`, nullable=False
  - `periodo: Mapped[str]` — `String(20)`, nullable=False
  - `fecha: Mapped[date]` — `Date`, nullable=False
  - `titulo: Mapped[str]` — `String(255)`, nullable=False
  - `__table_args__`: `UniqueConstraint("tenant_id", "materia_id", "cohorte_id", "tipo", "numero", "periodo", name="uq_fecha_academica_instancia")`
- [x] 2.2 Actualizar `backend/app/models/__init__.py` — exportar `FechaAcademica` y `TipoEvaluacion`

## 3. Migración 011

- [x] 3.1 Crear `backend/alembic/versions/a0b1c2d3e4f5_011_programa_materia_fecha_academica.py` (escribir a mano, NO `--autogenerate`):
  - `revision = "a0b1c2d3e4f5"`
  - `down_revision = "f9a0b1c2d3e4"`
  - `upgrade()`:
    1. `sa.Enum(TipoEvaluacion, name='tipo_evaluacion').create(op.get_bind(), checkfirst=True)`
    2. `op.create_table("programa_materia", ...)` — BaseEntityMixin columns + materia_id, carrera_id, cohorte_id, titulo, referencia_archivo, cargado_at; FKs RESTRICT; UniqueConstraint
    3. `op.create_table("fecha_academica", ...)` — BaseEntityMixin columns + materia_id, cohorte_id, tipo (Enum), numero, periodo, fecha, titulo; FKs RESTRICT; UniqueConstraint
    4. Indexes: `idx_programa_materia_tenant`, `idx_programa_materia_materia_cohorte`, `idx_fecha_academica_tenant`, `idx_fecha_academica_materia_cohorte`
  - `downgrade()`:
    1. Drop indexes
    2. `op.drop_table("fecha_academica")`, `op.drop_table("programa_materia")`
    3. `sa.Enum(name='tipo_evaluacion').drop(op.get_bind(), checkfirst=True)`
- [x] 3.2 Verificar `alembic upgrade head` en `trace_test` y `trace`
- [x] 3.3 Verificar round-trip: `alembic downgrade -1` → `alembic upgrade head`

## 4. Repositorios

- [x] 4.1 Crear `backend/app/repositories/programa_materia_repository.py`:
  - `ProgramaMateriaRepository(BaseRepository[ProgramaMateria])`
  - `model_class = ProgramaMateria`
  - `async def get_by_combinacion(self, materia_id, carrera_id, cohorte_id) -> ProgramaMateria | None` — filtra tenant_id + combinación + deleted_at.is_(None)
  - `async def list_by_materia(self, materia_id: UUID) -> list[ProgramaMateria]`
  - `async def list_by_cohorte(self, cohorte_id: UUID) -> list[ProgramaMateria]`
- [x] 4.2 Crear `backend/app/repositories/fecha_academica_repository.py`:
  - `FechaAcademicaRepository(BaseRepository[FechaAcademica])`
  - `model_class = FechaAcademica`
  - `async def get_by_instancia(self, materia_id, cohorte_id, tipo, numero, periodo) -> FechaAcademica | None`
  - `async def list_by_materia_cohorte(self, materia_id, cohorte_id, periodo=None) -> list[FechaAcademica]` — order by tipo, numero ASC
  - `async def list_by_cohorte(self, cohorte_id, periodo=None) -> list[FechaAcademica]`
- [x] 4.3 Actualizar `backend/app/repositories/__init__.py` — exportar los 2 nuevos repos

## 5. Schemas Pydantic (`backend/app/schemas/programas_y_fechas.py`)

Todos con `model_config = ConfigDict(extra='forbid')`.

- [x] 5.1 `ProgramaMateriaCreate`: `materia_id: UUID`, `carrera_id: UUID`, `cohorte_id: UUID`, `titulo: str (min=1, max=255)`, `referencia_archivo: str (min=1)`
- [x] 5.2 `ProgramaMateriaUpdate`: `titulo: str | None = None`, `referencia_archivo: str | None = None`
- [x] 5.3 `ProgramaMateriaResponse`: `id, tenant_id, materia_id, carrera_id, cohorte_id, titulo, referencia_archivo, cargado_at, created_at, updated_at` — `from_attributes=True`
- [x] 5.4 `FechaAcademicaCreate`: `materia_id: UUID`, `cohorte_id: UUID`, `tipo: TipoEvaluacion`, `numero: int (ge=1)`, `periodo: str (min=1, max=20)`, `fecha: date`, `titulo: str (min=1, max=255)`
- [x] 5.5 `FechaAcademicaUpdate`: `fecha: date | None = None`, `titulo: str | None = None`
- [x] 5.6 `FechaAcademicaResponse`: `id, tenant_id, materia_id, cohorte_id, tipo, numero, periodo, fecha, titulo, created_at, updated_at` — `from_attributes=True`

## 6. Servicio (`backend/app/services/programas_service.py`)

- [x] 6.1 `ProgramasService(session: AsyncSession)`:

  **ProgramaMateria:**
  - `create_programa(*, tenant_id, data: ProgramaMateriaCreate) → ProgramaMateria`:
    - Verifica `materia_id` en tenant → 404 si falta
    - Verifica `carrera_id` en tenant → 404 si falta
    - Verifica `cohorte_id` en tenant → 404 si falta
    - Unicidad por combinación → `ValueError("programa ya existe")` si existe (no deleted)
    - `repo.create({...data, tenant_id, cargado_at=now()})`
  - `update_programa(*, id, tenant_id, data: ProgramaMateriaUpdate) → ProgramaMateria`:
    - `repo.get_by_id(id)` → None → `ValueError("not found")`
    - `repo.update(id, data_dict)` (excluye None; `cargado_at` no se actualiza)
  - `delete_programa(*, id, tenant_id) → bool`:
    - `repo.soft_delete(id)` → False → `ValueError("not found")`
  - `list_programas(*, tenant_id, materia_id=None, carrera_id=None, cohorte_id=None) → list[ProgramaMateria]`
  - `get_programa(*, id, tenant_id) → ProgramaMateria`:
    - `repo.get_by_id(id)` → None → `ValueError("not found")`

  **FechaAcademica:**
  - `create_fecha(*, tenant_id, data: FechaAcademicaCreate) → FechaAcademica`:
    - Verifica `materia_id` en tenant → 404
    - Verifica `cohorte_id` en tenant → 404
    - Unicidad por instancia → `ValueError("fecha ya existe")`
    - `repo.create({...data, tenant_id})`
  - `update_fecha(*, id, tenant_id, data: FechaAcademicaUpdate) → FechaAcademica`
  - `delete_fecha(*, id, tenant_id) → bool`
  - `list_fechas(*, tenant_id, materia_id=None, cohorte_id=None, periodo=None) → list[FechaAcademica]`
  - `get_fecha(*, id, tenant_id) → FechaAcademica`
  - `generar_fragmento_lms(*, tenant_id, materia_id, cohorte_id, periodo=None) → str`:
    - Recupera fechas ordenadas (tipo canónico + numero ASC)
    - Genera Markdown agrupado por tipo (ver spec fecha-academica)
    - Devuelve `""` si no hay fechas

- [x] 6.2 Actualizar `backend/app/services/__init__.py` — exportar `ProgramasService`

## 7. Router (`backend/app/api/v1/routers/programas_y_fechas.py`)

- [x] 7.1 `router_programas = APIRouter(prefix="/api/v1/programas", tags=["programas"])`:
  - `GET /` — list programas (query: materia_id?, carrera_id?, cohorte_id?)
  - `POST /` — create 201
  - `GET /{id}` — get one
  - `PATCH /{id}` — update
  - `DELETE /{id}` — soft delete 204
  - Todos con `_ = Depends(_PERM_PROGRAMAS)` donde `_PERM_PROGRAMAS = require_permission("programas:gestionar")`
  - Mapeo ValueError → HTTPException según spec router

- [x] 7.2 `router_fechas = APIRouter(prefix="/api/v1/fechas-academicas", tags=["fechas-academicas"])` con `_PERM_FECHAS = require_permission("fechas_academicas:gestionar")`:
  - `GET /fragmento-lms` — **antes** de `/{id}` — query: materia_id, cohorte_id, periodo? → `{"fragmento": str}`
  - `GET /` — list fechas (query: materia_id?, cohorte_id?, periodo?)
  - `POST /` — create 201
  - `GET /{id}` — get one
  - `PATCH /{id}` — update
  - `DELETE /{id}` — soft delete 204

- [x] 7.3 Registrar en `backend/app/main.py`:
  ```python
  from app.api.v1.routers import programas_y_fechas
  app.include_router(programas_y_fechas.router_programas)
  app.include_router(programas_y_fechas.router_fechas)
  ```

## 8. Seed de permisos

- [x] 8.1 Actualizar `backend/scripts/seed_permissions.py`:
  - En `PERMISOS` (catálogo): agregar dos entradas:
    - `{"codigo": "programas:gestionar", "modulo": "programas", "descripcion": "Gestionar programas de materias"}`
    - `{"codigo": "fechas_academicas:gestionar", "modulo": "fechas_academicas", "descripcion": "Gestionar fechas académicas de evaluaciones"}`
  - En `PERMISSION_MATRIX["COORDINADOR"]`: agregar `"programas:gestionar": "all"` y `"fechas_academicas:gestionar": "all"`
  - En `PERMISSION_MATRIX["ADMIN"]`: agregar `"programas:gestionar": "all"` y `"fechas_academicas:gestionar": "all"`
  - `estructura_academica:gestionar` no se modifica (ADMIN-only, pertenece a C-06)

## 9. Tests (`backend/tests/test_programas_y_fechas.py`)

Usar fixture que provea 2 tenants: tenant A con admin+coordinador+profesor; tenant B con admin. Crear en DB Carrera/Cohorte/Materia para cada tenant (prerequisitos de C-06).

- [x] 9.1 `TestProgramaMateriaABM` (~10 tests):
  - `test_create_programa_ok` — POST 201, campos correctos
  - `test_create_programa_materia_otro_tenant_returns_404` — materia_id de tenant B → 404
  - `test_create_programa_carrera_otro_tenant_returns_404` — carrera_id de tenant B → 404
  - `test_create_programa_cohorte_otro_tenant_returns_404` — cohorte_id de tenant B → 404
  - `test_create_programa_duplicado_returns_409` — misma combinación → 409
  - `test_create_programa_misma_combinacion_otro_tenant_ok` — misma combinación en tenant B → 201 (aislamiento)
  - `test_list_programas_filtra_por_tenant` — list solo devuelve del tenant del actor
  - `test_get_programa_ok` — GET /{id} → 200
  - `test_get_programa_otro_tenant_returns_404`
  - `test_update_programa_ok` — PATCH titulo y referencia → 200; cargado_at no cambia
  - `test_soft_delete_programa_ok` — DELETE 204; GET → 404; existe en DB con deleted_at
  - `test_profesor_returns_403` — PROFESOR → 403
  - `test_coordinador_puede_crear` — COORDINADOR → 201

- [x] 9.2 `TestFechaAcademicaABM` (~10 tests):
  - `test_create_fecha_ok` — POST 201
  - `test_create_fecha_materia_otro_tenant_returns_404`
  - `test_create_fecha_cohorte_otro_tenant_returns_404`
  - `test_create_fecha_duplicada_returns_409` — mismo (materia, cohorte, tipo, numero, periodo) → 409
  - `test_create_fecha_misma_instancia_otro_tenant_ok` — aislamiento
  - `test_numero_invalido_returns_422` — numero=0 → 422 (Pydantic ge=1)
  - `test_list_fechas_ok`
  - `test_update_fecha_ok` — PATCH fecha y titulo → 200; tipo/numero/periodo no cambian
  - `test_soft_delete_fecha_ok`
  - `test_profesor_returns_403`
  - `test_coordinador_puede_gestionar`

- [x] 9.3 `TestFragmentoLMS` (~4 tests):
  - `test_fragmento_lms_con_fechas` — crea 3 fechas distintas → fragmento Markdown con secciones correctas
  - `test_fragmento_lms_sin_fechas_devuelve_vacio` — GET con materia_id/cohorte_id sin datos → `{"fragmento": ""}`, 200
  - `test_fragmento_lms_filtra_por_periodo` — 2 fechas en 2026-1, 1 en 2026-2 → filtrar por periodo devuelve solo las del período
  - `test_fragmento_lms_orden_canonico` — verifica que Parcial aparece antes que TP, y 1er antes que 2do dentro de cada tipo
