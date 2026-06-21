# Spec: Liquidación

> Sección 2 de C-18. Implementa `Liquidacion`, su repositorio, el `LiquidacionService` (cálculo + cierre + KPIs) y el router.

---

## Modelo `Liquidacion` (`backend/app/models/liquidacion.py`)

```python
class Liquidacion(Base, BaseEntityMixin):
    __tablename__ = "liquidacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cohorte_id", "usuario_id", "rol", "periodo",
            name="uq_liquidacion_docente_periodo",
        ),
    )

    cohorte_id: Mapped[UUID] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)        # "AAAA-MM"
    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False), nullable=False
    )
    comisiones: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default=sa.text("'[]'::json"), default=list
    )
    monto_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monto_plus: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    es_nexo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excluido_por_factura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    datos_bancarios_incompletos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estado: Mapped[LiquidacionEstado] = mapped_column(
        sa.Enum(LiquidacionEstado, name="liquidacion_estado", create_type=False),
        nullable=False,
        server_default=sa.text("'Abierta'"),
    )
```

**Notas:**
- `periodo` sigue el formato `"AAAA-MM"` (7 caracteres). El service valida el formato con regex antes de calcular.
- `comisiones` es desnormalizado (snapshot al momento del cálculo): cuando se cierra, el estado queda congelado aunque cambien las Asignaciones después.
- `datos_bancarios_incompletos` no está en E19 del KB — es extensión técnica para implementar RN-26 sin romper el cálculo.
- `total = 0` cuando `excluido_por_factura=True` (docente facturante — RN-35).

---

## Repositorio `LiquidacionRepository`

```python
class LiquidacionRepository(BaseRepository[Liquidacion]):
    model_class = Liquidacion

    async def find_by_docente_periodo(
        self, usuario_id: UUID, cohorte_id: UUID, rol: RolLiquidable, periodo: str
    ) -> Liquidacion | None:
        """Busca el registro exacto para el upsert del cálculo."""

    async def list_by_periodo(
        self, cohorte_id: UUID, periodo: str
    ) -> list[Liquidacion]:
        """Todos los docentes liquidados en (cohorte, periodo)."""

    async def list_cerradas(
        self, cohorte_id: UUID | None = None
    ) -> list[Liquidacion]:
        """Historial de liquidaciones cerradas — para F10.3."""

    async def cerrar_batch(
        self, cohorte_id: UUID, periodo: str
    ) -> int:
        """
        UPDATE liquidacion SET estado='Cerrada'
        WHERE tenant_id=... AND cohorte_id=... AND periodo=... AND estado='Abierta'.
        Retorna cantidad de filas actualizadas.
        """
```

---

## Service `LiquidacionService`

```python
class LiquidacionService:
    def __init__(
        self,
        session: AsyncSession,
        liquidacion_repo: LiquidacionRepository,
        salario_base_repo: SalarioBaseRepository,
        salario_plus_repo: SalarioPlusRepository,
        materia_grupo_repo: MateriaGrupoRepository,
        # repositorios existentes (no modificados)
        user_repo: UserRepository,
        asignacion_repo: AsignacionRepository,
        rol_repo: RolRepository,
    ):
```

### `calcular_liquidaciones_periodo`

```python
async def calcular_liquidaciones_periodo(
    self,
    *,
    tenant_id: UUID,
    cohorte_id: UUID,
    periodo: str,         # "AAAA-MM"
    actor_id: UUID,
) -> list[Liquidacion]:
```

**Algoritmo:**

```
fecha_inicio = date(int(periodo[:4]), int(periodo[5:]), 1)
fecha_fin    = last_day_of_month(fecha_inicio)

1. Obtener todas las Asignaciones activas en la cohorte durante el período:
   WHERE cohorte_id = cohorte_id
     AND tenant_id = tenant_id
     AND deleted_at IS NULL
     AND desde <= fecha_fin
     AND (hasta IS NULL OR hasta >= fecha_inicio)

2. Agrupar por (usuario_id, rol_id):
   Para cada grupo (docente, rol):

   a. Derivar rol_nombre = rol.nombre (JOIN Rol)
   b. Verificar que rol_nombre esté en RolLiquidable — saltar si no (ALUMNO, ADMIN, etc.)
   c. Obtener SalarioBase vigente:
        base_entry = salario_base_repo.find_vigente(rol=RolLiquidable(rol_nombre), fecha=fecha_inicio)
        monto_base = base_entry.monto if base_entry else Decimal("0.00")

   d. Para cada Asignacion del docente/rol con materia_id no nulo:
        grupos_materia = materia_grupo_repo.get_grupos_de_materia(asignacion.materia_id)
        Para cada grupo en grupos_materia:
          plus_entry = salario_plus_repo.find_vigente(grupo, RolLiquidable(rol_nombre), fecha_inicio)
          if plus_entry:
            n_comisiones += len(asignacion.comisiones)
            monto_plus += plus_entry.monto * n_comisiones

   e. total = monto_base + monto_plus
   f. es_nexo = (rol_nombre == "NEXO")

   g. Obtener usuario, descifrar banco/cbu/alias_cbu:
      datos_bancarios_incompletos = not (usuario.banco and usuario.cbu and usuario.alias_cbu)

   h. excluido_por_factura = usuario.facturador
      if excluido_por_factura:
          total = Decimal("0.00")

   i. comisiones_snapshot = flatten([a.comisiones for a in asignaciones_del_docente])

   j. Upsert:
      existente = liquidacion_repo.find_by_docente_periodo(...)
      if existente and existente.estado == LiquidacionEstado.Cerrada:
          continue  # no tocar cerradas
      if existente:
          actualizar campos (monto_base, monto_plus, total, flags, comisiones)
      else:
          crear nueva Liquidacion (estado=Abierta)

3. Retornar lista de Liquidaciones procesadas
```

**Nota sobre grupos:** el contador `n_comisiones` se lleva **por grupo** (no acumulado entre grupos). El pseudocódigo arriba necesita un `defaultdict` por grupo antes de sumar `monto_plus`.

### `cerrar_liquidaciones_periodo`

```python
async def cerrar_liquidaciones_periodo(
    self,
    *,
    tenant_id: UUID,
    cohorte_id: UUID,
    periodo: str,
    actor_id: UUID,
) -> int:
    """
    Cierra todas las liquidaciones Abiertas de (cohorte, periodo).
    Retorna cantidad de registros cerrados.
    Audita LIQUIDACION_CERRAR con filas_afectadas=count.
    """
    count = await self.liquidacion_repo.cerrar_batch(cohorte_id, periodo)
    await self.audit.log(
        action=LIQUIDACION_CERRAR,
        actor_id=actor_id,
        tenant_id=tenant_id,
        detalle={"cohorte_id": str(cohorte_id), "periodo": periodo},
        filas_afectadas=count,
    )
    return count
```

### `get_kpis_periodo`

```python
async def get_kpis_periodo(
    self, *, tenant_id: UUID, cohorte_id: UUID, periodo: str
) -> dict:
    """
    Retorna:
    {
      "total_sin_factura": Decimal,  # suma(total) where excluido_por_factura=False
      "total_con_factura": Decimal,  # suma(tamano... no. suma de facturas Abonadas del período)
      "count_docentes": int,
      "count_nexo": int,
      "count_facturantes": int,
      "count_sin_datos_bancarios": int,
    }
    """
```

`total_con_factura` = suma de `Factura.tamano_kb`... no, espera — es suma de los montos de las facturas. Pero `Factura` no tiene campo `monto` — solo `detalle` y `tamano_kb`. El KB no define un campo monto en Factura (E20).

⚠️ **Open question:** ¿cómo se calcula `total_con_factura` si Factura no tiene campo `monto`? En el KB RN-38 dice "total del universo de facturantes" pero E20 no incluye importe. Opciones:
- a) Sumar el `total` de las Liquidaciones de facturantes (aunque sea 0 — informativo)
- b) Agregar campo `monto` a Factura (no en KB E20 — scope creep)
- c) `total_con_factura = Decimal("0.00")` con nota "pendiente definición"

**Decisión provisional:** opción (c) — el KPI `total_con_factura` se calcula a partir del count de facturas Abonadas en el período, sin sumar importes. Si el negocio necesita importes en facturas, se agrega en una iteración posterior.

---

## Schemas (`backend/app/schemas/liquidaciones.py`)

```python
class LiquidacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    id: UUID
    tenant_id: UUID
    cohorte_id: UUID
    periodo: str
    usuario_id: UUID
    rol: RolLiquidable
    comisiones: list[str]
    monto_base: Decimal
    monto_plus: Decimal
    total: Decimal
    es_nexo: bool
    excluido_por_factura: bool
    datos_bancarios_incompletos: bool
    estado: LiquidacionEstado
    created_at: datetime
    updated_at: datetime

class LiquidacionPeriodoRequest(BaseModel):
    """Body para POST /calcular."""
    cohorte_id: UUID
    periodo: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]

class CerrarPeriodoRequest(BaseModel):
    """Body para POST /cerrar."""
    cohorte_id: UUID
    periodo: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]

class KpisPeriodoResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cohorte_id: UUID
    periodo: str
    total_sin_factura: Decimal
    total_con_factura: Decimal
    count_docentes: int
    count_nexo: int
    count_facturantes: int
    count_sin_datos_bancarios: int

class LiquidacionListResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    periodo: str
    cohorte_id: UUID
    estado_periodo: str    # "Abierto" | "Cerrado" (derivado: all Cerradas → Cerrado)
    kpis: KpisPeriodoResponse
    liquidaciones: list[LiquidacionResponse]
```

---

## Router (`backend/app/api/v1/routers/liquidaciones.py`)

Guard: `require_permission("liquidaciones:calcular_cerrar")` en todos los endpoints.
Prefix: `/api/v1/liquidaciones`
Tags: `["liquidaciones"]`

```
POST  /calcular
    body: LiquidacionPeriodoRequest
    response: LiquidacionListResponse (201)
    efecto: crea/actualiza liquidaciones Abiertas del período

POST  /cerrar
    body: CerrarPeriodoRequest
    response: {"cerradas": int} (200)
    efecto: cierra todas las liquidaciones Abiertas del período; audita LIQUIDACION_CERRAR

GET   /periodo
    query: cohorte_id, periodo
    response: LiquidacionListResponse (200)
    efecto: devuelve el estado actual del período (Abierto/Cerrado) + KPIs + detalle

GET   /historial
    query: cohorte_id? (opcional)
    response: list[{"cohorte_id", "periodo", "estado_periodo", "count_docentes"}] (200)
    efecto: lista de períodos cerrados (historial F10.3)

GET   /{id}
    response: LiquidacionResponse (200)
    efecto: detalle de una liquidación individual
```

**Mapeo de errores:**
- `ValueError("periodo_invalido")` → 422
- `ValueError("cohorte_otro_tenant")` → 404
- Períodos cerrados en el body de POST `/calcular` → no error, se omiten silenciosamente (devueltos con `estado=Cerrada`)

---

## Tests (`backend/tests/test_liquidaciones.py`)

Fixture: tenant A con FINANZAS-user, Cohorte C1, 4 docentes (PROFESOR sin factura, TUTOR sin factura, NEXO sin factura, PROFESOR con facturador=True), SalarioBase para PROFESOR/TUTOR/NEXO, SalarioPlus para grupo "PROG", MateriaGrupo mapeando materia M1 → "PROG", Asignaciones activas en C1 para el período "2026-06".

### TestCalculo (~8 tests)
- `test_calcular_base_sin_plus` — docente sin materia en grupo → total = solo base
- `test_calcular_con_plus_una_comision` — 1 comision en grupo PROG → total = base + plus × 1
- `test_calcular_con_plus_tres_comisiones` — comisiones=["A","B","C"] en PROG → base + plus × 3
- `test_calcular_facturador_excluido` — docente con facturador=True → excluido_por_factura=True, total=0
- `test_calcular_nexo_es_nexo_true` — docente NEXO → es_nexo=True, incluido en total_sin_factura
- `test_calcular_sin_datos_bancarios_flagueado` — usuario sin cbu → datos_bancarios_incompletos=True, no error
- `test_calcular_recalculo_abierta_ok` — segunda llamada con mismo período → actualiza valores
- `test_calcular_no_toca_cerradas` — si existe Cerrada, se omite en el recálculo

### TestCierre (~5 tests)
- `test_cerrar_periodo_ok` — POST /cerrar → todas pasan a Cerrada, retorna count
- `test_cerrar_periodo_audita_liquidacion_cerrar` — audit log generado con código LIQUIDACION_CERRAR
- `test_cerrar_ya_cerrado_idempotente` — cerrar un período ya cerrado → 0 filas cerradas, sin error
- `test_calcular_tras_cierre_no_modifica` — POST /calcular en período cerrado → responde con las cerradas, sin modificar
- `test_cierre_otro_cohorte_no_interfiere` — cohorte C2 no afecta cierre de C1

### TestKPIs (~4 tests)
- `test_kpis_total_sin_factura_correcto` — sum de totals no-facturantes
- `test_kpis_count_nexo_correcto`
- `test_kpis_count_facturantes_correcto`
- `test_kpis_sin_datos_bancarios_count`

### TestRBAC (~3 tests)
- `test_no_finanzas_calcular_returns_403` — COORDINADOR → 403
- `test_no_finanzas_cerrar_returns_403`
- `test_aislamiento_tenant` — FINANZAS de tenant B no ve datos de tenant A
