## 1. Modelos ORM (`backend/app/models/evaluacion.py`)

- [x] 1.1 Crear `backend/app/models/evaluacion.py` con 4 clases:

  **`EstadoReserva(str, enum.Enum)`**:
  - `Activa = "Activa"`, `Cancelada = "Cancelada"`

  **`Evaluacion(Base, BaseEntityMixin)`** — `__tablename__ = "evaluacion"`:
  - `materia_id: Mapped[UUID]` — `ForeignKey("materia.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `cohorte_id: Mapped[UUID]` — `ForeignKey("cohorte.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `tipo: Mapped[TipoEvaluacion]` — `sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False)`, nullable=False
  - `instancia: Mapped[str]` — `String(255)`, nullable=False
  - `dias_disponibles: Mapped[int]` — `Integer`, nullable=False
  - `cupo_total: Mapped[int]` — `Integer`, nullable=False, default=0
  - `__table_args__`: `UniqueConstraint("tenant_id", "materia_id", "cohorte_id", "tipo", "instancia", name="uq_evaluacion_instancia")`

  **`ConvocadoEvaluacion(Base, BaseEntityMixin)`** — `__tablename__ = "convocado_evaluacion"`:
  - `evaluacion_id: Mapped[UUID]` — `ForeignKey("evaluacion.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `usuario_id: Mapped[UUID | None]` — `ForeignKey("user.id", ondelete="SET NULL")`, nullable=True
  - `nombre: Mapped[str]` — `String(255)`, nullable=False (plaintext, como EntradaPadron)
  - `apellidos: Mapped[str]` — `String(255)`, nullable=False (plaintext)
  - `email_cifrado: Mapped[str]` — `EncryptedString` TypeDecorator (AES-256-GCM), nullable=False
  - `email_hash: Mapped[str]` — `String(64)`, nullable=False — HMAC-SHA256 blind index
  - `__table_args__`:
    - `UniqueConstraint("tenant_id", "evaluacion_id", "usuario_id", name="uq_convocado_evaluacion_usuario")`
    - `Index("idx_convocado_email_hash", "tenant_id", "evaluacion_id", "email_hash")`

  **`ReservaEvaluacion(Base, BaseEntityMixin)`** — `__tablename__ = "reserva_evaluacion"`:
  - `evaluacion_id: Mapped[UUID]` — `ForeignKey("evaluacion.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `alumno_id: Mapped[UUID]` — `ForeignKey("usuario.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `fecha_hora: Mapped[datetime]` — `DateTime(timezone=True)`, nullable=False
  - `estado: Mapped[EstadoReserva]` — `sa.Enum(EstadoReserva, name="estado_reserva", create_type=True)`, nullable=False, default=EstadoReserva.Activa
  - `__table_args__`: `UniqueConstraint("tenant_id", "evaluacion_id", "alumno_id", name="uq_reserva_evaluacion_alumno")`

  **`ResultadoEvaluacion(Base, BaseEntityMixin)`** — `__tablename__ = "resultado_evaluacion"`:
  - `evaluacion_id: Mapped[UUID]` — `ForeignKey("evaluacion.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `alumno_id: Mapped[UUID]` — `ForeignKey("usuario.id", ondelete="RESTRICT")`, nullable=False, index=True
  - `nota_final: Mapped[str]` — `String(255)`, nullable=False
  - `__table_args__`: `UniqueConstraint("tenant_id", "evaluacion_id", "alumno_id", name="uq_resultado_evaluacion_alumno")`

- [x] 1.2 Actualizar `backend/app/models/__init__.py` — exportar `Evaluacion`, `ConvocadoEvaluacion`, `ReservaEvaluacion`, `ResultadoEvaluacion`, `EstadoReserva`

## 2. Migración 012

- [x] 2.1 Crear `backend/alembic/versions/b1c2d3e4f5a6_012_evaluacion_reserva_resultado.py` (escribir a mano, NO `--autogenerate`):
  - `revision = "b1c2d3e4f5a6"`
  - `down_revision = "a0b1c2d3e4f5"` (011 — C-17)
  - `upgrade()`:
    1. `op.create_table("evaluacion", ...)` — BaseEntityMixin columns + materia_id, cohorte_id, tipo (`Enum("tipo_evaluacion", schema=None, create_type=False)`), instancia, dias_disponibles, cupo_total; FKs RESTRICT; UniqueConstraint
    2. `op.create_table("convocado_evaluacion", ...)` — BaseEntityMixin + evaluacion_id, usuario_id (nullable), nombre, apellidos, email; FKs RESTRICT; UniqueConstraint
    3. `sa.Enum("Activa", "Cancelada", name="estado_reserva").create(op.get_bind(), checkfirst=True)`
    4. `op.create_table("reserva_evaluacion", ...)` — BaseEntityMixin + evaluacion_id, alumno_id, fecha_hora, estado; FKs RESTRICT; UniqueConstraint
    5. `op.create_table("resultado_evaluacion", ...)` — BaseEntityMixin + evaluacion_id, alumno_id, nota_final; FKs RESTRICT; UniqueConstraint
    6. Índices: `idx_evaluacion_tenant`, `idx_evaluacion_materia_cohorte`, `idx_convocado_evaluacion_id`, `idx_reserva_evaluacion_id`, `idx_reserva_alumno_id`, `idx_resultado_evaluacion_id`
  - `downgrade()`:
    1. Drop índices
    2. Drop tablas en orden: `resultado_evaluacion`, `reserva_evaluacion`, `convocado_evaluacion`, `evaluacion`
    3. `sa.Enum(name="estado_reserva").drop(op.get_bind(), checkfirst=True)`
    4. **NO tocar `tipo_evaluacion`** — pertenece a C-17 (migración 011)
- [x] 2.2 Verificar `alembic upgrade head` en `trace_test` y `trace`
- [x] 2.3 Verificar round-trip: `alembic downgrade -1` → `alembic upgrade head`

## 3. Repositorios (`backend/app/repositories/evaluacion_repository.py`)

- [x] 3.1 Crear `EvaluacionRepository(BaseRepository[Evaluacion])`:
  - `model_class = Evaluacion`
  - `async def get_by_instancia(self, materia_id, cohorte_id, tipo, instancia) → Evaluacion | None`
  - `async def list_by_materia_cohorte(self, materia_id, cohorte_id) → list[Evaluacion]`
  - `async def count_reservas_activas(self, evaluacion_id: UUID) → int` — COUNT sobre `reserva_evaluacion` WHERE estado='Activa' AND deleted_at IS NULL
  - `async def count_convocados(self, evaluacion_id: UUID) → int`
  - `async def count_resultados(self, evaluacion_id: UUID) → int`

- [x] 3.2 Crear `ConvocadoRepository(BaseRepository[ConvocadoEvaluacion])`:
  - `async def list_by_evaluacion(self, evaluacion_id: UUID) → list[ConvocadoEvaluacion]`
  - `async def get_by_email_hash(self, evaluacion_id: UUID, email_hash: str) → ConvocadoEvaluacion | None`
  - `async def bulk_create(self, tenant_id: UUID, evaluacion_id: UUID, filas: list[dict]) → int`:
    - Para filas con `usuario_id` → skip si ya existe en `(evaluacion_id, usuario_id)`
    - Para filas sin `usuario_id` → skip si `email_hash` ya existe en la misma `evaluacion_id` (via `get_by_email_hash`)
    - Cada fila: `email_cifrado = EncryptedString` (TypeDecorator cifra automáticamente), `email_hash = hmac_email(row.email)`

- [x] 3.3 Crear `ReservaRepository(BaseRepository[ReservaEvaluacion])`:
  - `async def get_activa_by_alumno(self, evaluacion_id: UUID, alumno_id: UUID) → ReservaEvaluacion | None`
  - `async def get_any_by_alumno(self, evaluacion_id: UUID, alumno_id: UUID) → ReservaEvaluacion | None` — incluye canceladas (para soft-delete antes de re-reservar)
  - `async def list_activas_by_evaluacion(self, evaluacion_id: UUID) → list[ReservaEvaluacion]`
  - `async def count_activas(self, evaluacion_id: UUID) → int`

- [x] 3.4 Crear `ResultadoRepository(BaseRepository[ResultadoEvaluacion])`:
  - `async def get_by_alumno(self, evaluacion_id: UUID, alumno_id: UUID) → ResultadoEvaluacion | None`
  - `async def list_by_evaluacion(self, evaluacion_id: UUID) → list[ResultadoEvaluacion]`

- [x] 3.5 Actualizar `backend/app/repositories/__init__.py` — exportar los 4 nuevos repos

## 4. Schemas Pydantic (`backend/app/schemas/coloquios.py`)

Todos los schemas con `model_config = ConfigDict(extra='forbid')`.

- [x] 4.1 `EvaluacionCreate`: `materia_id: UUID`, `cohorte_id: UUID`, `tipo: TipoEvaluacion`, `instancia: str (min=1, max=255)`, `dias_disponibles: int (ge=1)`, `cupo_total: int (ge=0)`
- [x] 4.2 `EvaluacionUpdate`: `instancia: str | None`, `dias_disponibles: int | None (ge=1)`, `cupo_total: int | None (ge=0)`
- [x] 4.3 `EvaluacionResponse`: `id, tenant_id, materia_id, cohorte_id, tipo, instancia, dias_disponibles, cupo_total, created_at, updated_at` + `from_attributes=True`
- [x] 4.4 `MetricasConvocatoria`: `evaluacion_id, convocados, reservas_activas, cupos_libres, notas_registradas`
- [x] 4.5 `MetricasPanel`: `total_alumnos_cargados, instancias_activas, reservas_activas, notas_registradas`
- [x] 4.6 `ConvocadoImportRow`: `nombre: str (min=1)`, `apellidos: str (min=1)`, `email: str (min=1)`, `usuario_id: UUID | None = None`
- [x] 4.7 `ConvocadoImportRequest`: `filas: list[ConvocadoImportRow] (min_length=1)`
- [x] 4.8 `ConvocadoImportResponse`: `insertados: int`
- [x] 4.9 `ReservaCreate`: `fecha_hora: datetime`
- [x] 4.10 `ReservaResponse`: `id, tenant_id, evaluacion_id, alumno_id, fecha_hora, estado, created_at, updated_at` + `from_attributes=True`
- [x] 4.11 `ResultadoCreate`: `alumno_id: UUID`, `nota_final: str (min=1, max=255)`
- [x] 4.12 `ResultadoResponse`: `id, tenant_id, evaluacion_id, alumno_id, nota_final, created_at` + `from_attributes=True`
- [x] 4.13 Actualizar `backend/app/schemas/__init__.py` — exportar el módulo

## 5. Servicio (`backend/app/services/coloquios_service.py`)

- [x] 5.1 Crear `ColoquiosService(session: AsyncSession)` con todos los métodos descritos en design.md §D6:

  **Convocatorias:**
  - `create_convocatoria(*, tenant_id, data: EvaluacionCreate) → Evaluacion`:
    - Verifica `materia_id` en tenant → ValueError("materia_not_found")
    - Verifica `cohorte_id` en tenant → ValueError("cohorte_not_found")
    - Unicidad instancia → ValueError("already_exists")
    - `repo.create({...data, tenant_id})`
  - `update_convocatoria(*, id, tenant_id, data: EvaluacionUpdate) → Evaluacion`
  - `delete_convocatoria(*, id, tenant_id) → None`
  - `list_convocatorias(*, tenant_id, materia_id=None, cohorte_id=None, tipo=None) → list[Evaluacion]`
  - `get_convocatoria(*, id, tenant_id) → Evaluacion`

  **Convocados:**
  - `importar_convocados(*, tenant_id, evaluacion_id, data: ConvocadoImportRequest) → int`:
    - Verifica evaluacion en tenant → ValueError("not_found")
    - Para cada fila: calcula `email_hash = hmac_email(row.email)` (EncryptedString cifra automáticamente `email_cifrado` en el ORM)
    - `convocado_repo.bulk_create(tenant_id, evaluacion_id, filas_procesadas)` donde cada fila incluye `email_cifrado=row.email, email_hash=hash`
    - Devuelve `insertados`

  **Métricas:**
  - `metricas_panel(*, tenant_id) → MetricasPanel`
  - `metricas_convocatoria(*, evaluacion_id, tenant_id) → MetricasConvocatoria`:
    - `convocados = await repo.count_convocados(evaluacion_id)`
    - `activas = await repo.count_reservas_activas(evaluacion_id)`
    - `cupos_libres = -1 if cupo_total == 0 else max(0, cupo_total - activas)`
    - `notas = await repo.count_resultados(evaluacion_id)`

  **Reservas:**
  - `reservar_turno(*, evaluacion_id, alumno_id, fecha_hora, tenant_id) → ReservaEvaluacion`:
    - Verifica evaluacion en tenant → ValueError("not_found")
    - Verifica cupo (SELECT FOR UPDATE sobre evaluacion): si `cupo_total > 0 and activas >= cupo_total` → ValueError("sin_cupo")
    - Verifica reserva activa previa → ValueError("reserva_already_active")
    - Si hay reserva cancelada previa (unique constraint): soft-delete antes de insertar nueva
    - Inserta con estado=Activa
  - `cancelar_reserva(*, reserva_id, alumno_id, tenant_id) → ReservaEvaluacion`:
    - Obtiene reserva → ValueError("not_found") si no existe o no pertenece al alumno
    - Si `estado == Cancelada` → ValueError("reserva_already_cancelled")
    - Actualiza `estado = Cancelada`

  **Resultados:**
  - `registrar_resultado(*, evaluacion_id, alumno_id, nota_final, tenant_id, actor_id) → ResultadoEvaluacion`:
    - Verifica evaluacion en tenant → ValueError("not_found")
    - Verifica alumno en tenant → ValueError("alumno_not_found")
    - Si NO existe resultado → INSERT nuevo ResultadoEvaluacion
    - Si SÍ existe → UPDATE nota_final + `AuditService.log(RESULTADO_REGISTRAR, detalle={"nota_anterior": old, "nota_nueva": new, "alumno_id": str(alumno_id)})`
  - `list_resultados(*, evaluacion_id, tenant_id) → list[ResultadoEvaluacion]`
  - `list_reservas(*, evaluacion_id, tenant_id) → list[ReservaEvaluacion]`

- [x] 5.2 Actualizar `backend/app/services/__init__.py` — exportar `ColoquiosService`

## 6. Router (`backend/app/api/v1/routers/coloquios.py`)

- [x] 6.1 Definir `router = APIRouter(prefix="/api/v1/coloquios", tags=["coloquios"])`
- [x] 6.2 Implementar todos los endpoints de gestión (`_PERM_GESTION = require_permission("coloquios:gestionar")`):
  - `GET /` — list_convocatorias (query: materia_id?, cohorte_id?, tipo?)
  - `POST /` — create_convocatoria → 201
  - `GET /metricas-panel` — **antes** de `/{id}` en el router
  - `GET /{id}` — get_convocatoria
  - `PATCH /{id}` — update_convocatoria
  - `DELETE /{id}` — 204
  - `POST /{id}/convocados` — importar_convocados
  - `GET /{id}/metricas` — metricas_convocatoria
  - `GET /{id}/reservas` — list_reservas (agenda F7.5)
  - `POST /{id}/resultados` — registrar_resultado → 201
  - `GET /{id}/resultados` — list_resultados
- [x] 6.3 Implementar endpoints de reserva (`_PERM_RESERVAR = require_permission("evaluacion:reservar")`):
  - `POST /{id}/mis-reservas` — reservar_turno → 201
  - `DELETE /{id}/mis-reservas/{reserva_id}` — cancelar_reserva → 200
- [x] 6.4 Mapear `ValueError` → `HTTPException` según tabla de spec coloquios-router
- [x] 6.5 Registrar router en `backend/app/main.py`:
  ```python
  from app.api.v1.routers import coloquios
  app.include_router(coloquios.router)
  ```

## 7. Audit codes

- [x] 7.0 Actualizar `backend/app/core/audit_codes.py`:
  - Agregar constante `RESULTADO_REGISTRAR = "RESULTADO_REGISTRAR"` (sección `# C-14`)
  - Agregar `RESULTADO_REGISTRAR` al `frozenset` `VALID_ACTION_CODES`

## 9. Seed de permisos

- [x] 7.1 Actualizar `backend/scripts/seed_permissions.py`:
  - En `PERMISOS` (catálogo): agregar entrada:
    - `{"codigo": "coloquios:gestionar", "modulo": "coloquios", "descripcion": "Gestionar convocatorias de evaluación (coloquios)"}`
  - En `PERMISSION_MATRIX["COORDINADOR"]`: agregar `"coloquios:gestionar": "all"`
  - En `PERMISSION_MATRIX["ADMIN"]`: agregar `"coloquios:gestionar": "all"`
  - `evaluacion:reservar` ya sembrado — NO modificar

## 10. Tests (`backend/tests/test_coloquios.py`)

Fixture: 2 tenants (A y B). Tenant A con admin + coordinador + profesor + alumno. Tenant B
con admin. Cada tenant con Carrera, Cohorte, Materia (prerequisitos de C-06).

- [x] 8.1 `TestCRUDConvocatoria` (~10 tests):
  - `test_create_convocatoria_ok` — POST 201, campos correctos
  - `test_create_convocatoria_materia_otro_tenant_404`
  - `test_create_convocatoria_cohorte_otro_tenant_404`
  - `test_create_convocatoria_duplicada_409` — misma (materia, cohorte, tipo, instancia) → 409
  - `test_create_convocatoria_mismo_tenant_b_ok` — aislamiento: misma combinación en tenant B → 201
  - `test_list_convocatorias_filtra_tenant`
  - `test_get_convocatoria_ok`
  - `test_get_convocatoria_otro_tenant_404`
  - `test_update_convocatoria_ok` — PATCH instancia y cupo_total
  - `test_soft_delete_convocatoria_ok` — DELETE 204; GET → 404; persiste en DB con deleted_at
  - `test_profesor_returns_403_en_gestion`
  - `test_coordinador_puede_crear`

- [x] 8.2 `TestImportarConvocados` (~5 tests):
  - `test_importar_convocados_ok` — POST /{id}/convocados → 200, insertados=N
  - `test_importar_convocados_idempotente` — reinsertar mismo usuario_id → insertados=0
  - `test_importar_convocados_evaluacion_otro_tenant_404`
  - `test_importar_convocados_sin_usuario_id_ok` — usuario_id=None se inserta siempre
  - `test_importar_convocados_lote_vacio_422` — filas=[] → 422

- [x] 8.3 `TestReservaTurno` (~8 tests):
  - `test_reservar_turno_ok` — alumno reserva → 201, estado=Activa
  - `test_reservar_turno_cupo_agotado_409` — cupo_total=1, 1 activa → segunda reserva → 409
  - `test_reservar_turno_sin_limite_ok` — cupo_total=0, N reservas → siempre 201
  - `test_reservar_turno_duplicado_activo_409` — mismo alumno reserva dos veces → 409
  - `test_reservar_turno_tras_cancelar_ok` — alumno cancela → vuelve a reservar → 201
  - `test_cancelar_reserva_ok` — DELETE /{id}/mis-reservas/{rid} → estado=Cancelada
  - `test_cancelar_reserva_ya_cancelada_409`
  - `test_cancelar_reserva_de_otro_alumno_403`

- [x] 8.4 `TestMetricas` (~5 tests):
  - `test_metricas_convocatoria_ok` — crea 3 convocados, 2 reservas activas, 1 resultado →
    convocados=3, reservas_activas=2, cupos_libres=cupo_total-2, notas_registradas=1
  - `test_metricas_cupo_ilimitado` — cupo_total=0 → cupos_libres=-1
  - `test_metricas_panel_ok` — agrega correctamente por tenant
  - `test_metricas_panel_tenant_aislamiento` — métricas de tenant A no incluyen datos de tenant B

- [x] 8.5 `TestResultados` (~4 tests):
  - `test_registrar_resultado_ok` — POST /{id}/resultados → 201, nota_final guardada
  - `test_registrar_resultado_reemplaza_anterior` — segunda nota → soft-delete del anterior + 201
  - `test_list_resultados_ok` — GET /{id}/resultados → lista correcta
  - `test_registrar_resultado_alumno_otro_tenant_404`
