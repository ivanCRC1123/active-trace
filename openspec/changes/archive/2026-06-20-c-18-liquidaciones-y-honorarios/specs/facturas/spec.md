# Spec: Facturas

> Sección 3 de C-18. Implementa `Factura`, su repositorio, `FacturaService` y el router. Flujo paralelo a la liquidación para docentes con `facturador=True`.

---

## Modelo `Factura` (`backend/app/models/factura.py`)

```python
class Factura(Base, BaseEntityMixin):
    __tablename__ = "factura"

    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)     # "AAAA-MM"
    detalle: Mapped[str] = mapped_column(Text, nullable=False)
    referencia_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    tamano_kb: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    estado: Mapped[FacturaEstado] = mapped_column(
        sa.Enum(FacturaEstado, name="factura_estado", create_type=False),
        nullable=False,
        server_default=sa.text("'Pendiente'"),
    )
    cargada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    abonada_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

**Invariantes:**
- `estado` solo puede ser `Pendiente` o `Abonada` (RN-39).
- Transición `Pendiente → Abonada` es unidireccional; no se puede revertir.
- `abonada_at` se setea automáticamente al abonar; es `NULL` mientras está Pendiente.
- `referencia_archivo` es un string opaco — igual al patrón de `ProgramaMateria` en C-17 (OD-9 de design.md). No se interpreta ni valida su contenido.
- `tamano_kb`: `Numeric(12, 3)` — tres decimales para precisión de KB. Nunca Float.
- La entidad permite múltiples facturas por docente en el mismo período (no hay UniqueConstraint en (usuario_id, periodo)).

---

## Repositorio `FacturaRepository`

```python
class FacturaRepository(BaseRepository[Factura]):
    model_class = Factura

    async def list_by_usuario(
        self, usuario_id: UUID
    ) -> list[Factura]:
        """Todas las facturas del docente, ordenadas por cargada_at DESC."""

    async def list_by_periodo(
        self, periodo: str
    ) -> list[Factura]:
        """Facturas del período para el tenant."""

    async def list_filtered(
        self,
        usuario_id: UUID | None = None,
        periodo: str | None = None,
        estado: FacturaEstado | None = None,
    ) -> list[Factura]:
        """Lista con filtros combinables — para F10.5."""

    async def abonar(self, factura_id: UUID, abonada_at: datetime) -> Factura | None:
        """
        UPDATE factura SET estado='Abonada', abonada_at=abonada_at
        WHERE id=factura_id AND tenant_id=... AND estado='Pendiente'.
        Retorna el objeto actualizado, o None si no existe o ya estaba abonada.
        """
```

---

## Service `FacturaService`

```python
class FacturaService:
    def __init__(
        self,
        session: AsyncSession,
        factura_repo: FacturaRepository,
        user_repo: UserRepository,     # para verificar facturador=True
        audit_service: AuditService,
    ):
```

### `crear_factura`

```python
async def crear_factura(
    self,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    data: FacturaCreate,
) -> Factura:
    """
    1. Verifica que data.usuario_id pertenece al tenant → 404 si no
    2. Verifica que usuario.facturador == True → ValueError("no_es_facturador") → 422
    3. Crea Factura(estado=Pendiente, cargada_at=now(), abonada_at=None)
    4. No audita la creación (KB no define código para "FACTURA_CARGAR")
    """
```

### `abonar_factura`

```python
async def abonar_factura(
    self,
    *,
    tenant_id: UUID,
    factura_id: UUID,
    actor_id: UUID,
) -> Factura:
    """
    1. Get factura → 404 si no existe en tenant
    2. Si estado == Abonada → ValueError("ya_abonada") → 409 (idempotente o error — ver open question)
    3. UPDATE estado=Abonada, abonada_at=now()
    4. Audita FACTURA_ABONAR
    """
    factura = await self.factura_repo.abonar(factura_id, abonada_at=datetime.now(UTC))
    if factura is None:
        raise ValueError("not_found_or_ya_abonada")
    await self.audit_service.log(
        action=FACTURA_ABONAR,
        actor_id=actor_id,
        tenant_id=tenant_id,
        detalle={"factura_id": str(factura_id), "usuario_id": str(factura.usuario_id)},
        filas_afectadas=1,
    )
    return factura
```

### `list_facturas`

```python
async def list_facturas(
    self,
    *,
    tenant_id: UUID,
    usuario_id: UUID | None = None,
    periodo: str | None = None,
    estado: FacturaEstado | None = None,
) -> list[Factura]:
```

### `get_factura`

```python
async def get_factura(self, *, tenant_id: UUID, factura_id: UUID) -> Factura:
    # → 404 si no existe en tenant
```

### `eliminar_factura`

```python
async def eliminar_factura(self, *, tenant_id: UUID, factura_id: UUID, actor_id: UUID) -> None:
    """
    Soft delete solo si estado==Pendiente.
    Si estado==Abonada → ValueError("no_se_puede_eliminar_abonada") → 422.
    No audita la eliminación (no hay código KB definido para esto).
    """
```

**Open question:** ¿puede eliminarse (soft-delete) una factura Abonada? Por ahora: no. Una factura abonada es un registro contable permanente.

---

## Schemas (`backend/app/schemas/facturas.py`)

```python
class FacturaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    usuario_id: UUID
    periodo: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]
    detalle: Annotated[str, StringConstraints(min_length=1)]
    referencia_archivo: Annotated[str, StringConstraints(min_length=1)]
    tamano_kb: Annotated[Decimal, Field(gt=0, decimal_places=3)]

class FacturaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    id: UUID
    tenant_id: UUID
    usuario_id: UUID
    periodo: str
    detalle: str
    referencia_archivo: str
    tamano_kb: Decimal
    estado: FacturaEstado
    cargada_at: datetime
    abonada_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

No existe `FacturaUpdate` — las facturas no se editan, solo se abonan. Si hay un error en los datos cargados, se debe soft-delete la factura incorrecta y crear una nueva.

---

## Router (`backend/app/api/v1/routers/facturas.py`)

Guard: `require_permission("facturas:gestionar")` en todos los endpoints.
Prefix: `/api/v1/facturas`
Tags: `["facturas"]`

```
GET    /
    query: usuario_id?, periodo?, estado? (Pendiente|Abonada)
    response: list[FacturaResponse] (200)
    efecto: lista con filtros — F10.5

POST   /
    body: FacturaCreate
    response: FacturaResponse (201)
    efecto: crea factura para docente facturador

GET    /{id}
    response: FacturaResponse (200)

POST   /{id}/abonar
    body: {} (vacío)
    response: FacturaResponse (200)
    efecto: Pendiente → Abonada; audita FACTURA_ABONAR

DELETE /{id}
    response: 204
    efecto: soft-delete si Pendiente; 422 si Abonada
```

**Mapeo de errores:**
- `ValueError("no_es_facturador")` → 422 `{"detail": "El docente no tiene modalidad de facturación."}`
- `ValueError("ya_abonada")` → 409 `{"detail": "La factura ya fue abonada."}`
- `ValueError("no_se_puede_eliminar_abonada")` → 422 `{"detail": "No se puede eliminar una factura abonada."}`
- `ValueError("not_found")` → 404
- `ValueError("usuario_otro_tenant")` → 404

---

## Tests (`backend/tests/test_facturas.py`)

Fixture: tenant A con FINANZAS-user; docente-A con `facturador=True`; docente-B con `facturador=False`.

### TestFacturaCRUD (~8 tests)
- `test_crear_factura_ok` — POST 201; estado=Pendiente; abonada_at=None
- `test_crear_factura_no_facturador_returns_422` — docente-B → 422
- `test_crear_factura_usuario_otro_tenant_returns_404`
- `test_get_factura_ok` — GET /{id} → 200
- `test_get_factura_otro_tenant_returns_404`
- `test_list_facturas_sin_filtros` — list todas del tenant
- `test_list_facturas_filtra_por_periodo` — solo "2026-06"
- `test_list_facturas_filtra_por_estado` — solo Pendientes

### TestAbonar (~5 tests)
- `test_abonar_factura_ok` — POST /abonar → estado=Abonada, abonada_at seteado
- `test_abonar_genera_audit_factura_abonar` — audit log con código FACTURA_ABONAR
- `test_abonar_ya_abonada_returns_409`
- `test_abonar_otro_tenant_returns_404`
- `test_abonar_factura_pendiente_idempotente_si_se_reintenta` — segunda llamada → 409

### TestEliminar (~3 tests)
- `test_delete_factura_pendiente_ok` — DELETE 204; GET → 404; soft-delete en DB
- `test_delete_factura_abonada_returns_422`
- `test_no_finanzas_returns_403` — COORDINADOR → 403 en cualquier endpoint

### TestRBAC (1 test)
- `test_aislamiento_tenant` — FINANZAS tenant B no puede ver facturas de tenant A
