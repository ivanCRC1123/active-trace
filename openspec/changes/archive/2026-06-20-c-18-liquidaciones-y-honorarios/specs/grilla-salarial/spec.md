# Spec: Grilla Salarial

> Sección 1 de C-18. Implementa `MateriaGrupo`, `SalarioBase`, `SalarioPlus` y sus repositorios, schemas y router.

---

## Modelos

### `MateriaGrupo` (`backend/app/models/materia_grupo.py`)

Resuelve el gap PA-22: mapea materias a claves de grupo de plus (ver design.md OD-1).

```python
class MateriaGrupo(Base, BaseEntityMixin):
    __tablename__ = "materia_grupo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "grupo",
            name="uq_materia_grupo_tenant_materia_grupo",
        ),
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    grupo: Mapped[str] = mapped_column(String(50), nullable=False)
```

- `grupo` es un string libre (ej. `"PROG"`, `"BD"`, `"ING"`). No hay enum de grupos — es configurable por tenant.
- Una materia puede pertenecer a más de un grupo (UniqueConstraint es `(materia, grupo)`, no solo `(materia)`).
- Soft-delete a través de `BaseEntityMixin.deleted_at`.

### `SalarioBase` (`backend/app/models/salario_base.py`)

```python
class SalarioBase(Base, BaseEntityMixin):
    __tablename__ = "salario_base"
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False),
        nullable=False,
        index=True,
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
```

- `monto` es `Numeric(12, 2)` — nunca Float.
- `hasta=None` significa vigencia abierta.
- Regla de negocio (validada en service): solo una entrada vigente por `(tenant_id, rol)` en un instante. Un intento de crear una segunda entrada vigente solapada → 409.

### `SalarioPlus` (`backend/app/models/salario_plus.py`)

```python
class SalarioPlus(Base, BaseEntityMixin):
    __tablename__ = "salario_plus"
    grupo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False),
        nullable=False,
        index=True,
    )
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
```

- Regla de negocio: solo un Plus vigente por `(tenant_id, grupo, rol)` en un instante.
- La clave `grupo` debe coincidir con valores usados en `MateriaGrupo.grupo` del mismo tenant — el service valida advertencia (no bloquea) si el grupo de un Plus no tiene materias mapeadas.

---

## Repositorios

### `MateriaGrupoRepository`

```python
class MateriaGrupoRepository(BaseRepository[MateriaGrupo]):
    model_class = MateriaGrupo

    async def get_grupos_de_materia(
        self, materia_id: UUID
    ) -> list[str]:
        """Retorna los grupos (strings) a los que pertenece la materia."""

    async def get_materias_de_grupo(
        self, grupo: str
    ) -> list[UUID]:
        """Retorna los materia_id que pertenecen al grupo dentro del tenant."""

    async def find_by_materia_grupo(
        self, materia_id: UUID, grupo: str
    ) -> MateriaGrupo | None:
        """Busca el mapeo específico (para crear sin duplicar)."""
```

### `SalarioBaseRepository`

```python
class SalarioBaseRepository(BaseRepository[SalarioBase]):
    model_class = SalarioBase

    async def find_vigente(
        self, rol: RolLiquidable, fecha: date
    ) -> SalarioBase | None:
        """
        Busca el SalarioBase vigente para (rol, fecha):
        desde <= fecha AND (hasta IS NULL OR hasta >= fecha).
        """

    async def find_solapados(
        self, rol: RolLiquidable, desde: date, hasta: date | None, excluir_id: UUID | None = None
    ) -> list[SalarioBase]:
        """
        Detecta registros cuyo rango se solapa con (desde, hasta).
        Usado en el service para validar unicidad de vigencia.
        """

    async def list_by_rol(self, rol: RolLiquidable) -> list[SalarioBase]:
        """Lista todos (activos) para un rol, ordenados por desde DESC."""
```

### `SalarioPlusRepository`

```python
class SalarioPlusRepository(BaseRepository[SalarioPlus]):
    model_class = SalarioPlus

    async def find_vigente(
        self, grupo: str, rol: RolLiquidable, fecha: date
    ) -> SalarioPlus | None:

    async def find_solapados(
        self, grupo: str, rol: RolLiquidable, desde: date, hasta: date | None,
        excluir_id: UUID | None = None
    ) -> list[SalarioPlus]:

    async def list_vigentes_para_periodo(
        self, fecha_inicio: date, fecha_fin: date
    ) -> list[SalarioPlus]:
        """Todos los plus vigentes en el período — usado por el cálculo de liquidación."""
```

---

## Schemas Pydantic (`backend/app/schemas/grilla_salarial.py`)

Todos con `model_config = ConfigDict(extra='forbid')`.

```python
# MateriaGrupo
class MateriaGrupoCreate(BaseModel):
    materia_id: UUID
    grupo: Annotated[str, StringConstraints(min_length=1, max_length=50)]

class MateriaGrupoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    id: UUID
    tenant_id: UUID
    materia_id: UUID
    grupo: str
    created_at: datetime
    updated_at: datetime

# SalarioBase
class SalarioBaseCreate(BaseModel):
    rol: RolLiquidable
    monto: Annotated[Decimal, Field(gt=0, decimal_places=2)]
    desde: date
    hasta: date | None = None

class SalarioBaseUpdate(BaseModel):
    monto: Annotated[Decimal, Field(gt=0, decimal_places=2)] | None = None
    hasta: date | None = None  # solo se puede cambiar el fin; rol y desde son inmutables

class SalarioBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    id: UUID
    tenant_id: UUID
    rol: RolLiquidable
    monto: Decimal
    desde: date
    hasta: date | None
    created_at: datetime
    updated_at: datetime

# SalarioPlus — análogo a SalarioBase más campos grupo y descripcion
class SalarioPlusCreate(BaseModel):
    grupo: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    rol: RolLiquidable
    descripcion: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    monto: Annotated[Decimal, Field(gt=0, decimal_places=2)]
    desde: date
    hasta: date | None = None

class SalarioPlusUpdate(BaseModel):
    descripcion: str | None = None
    monto: Annotated[Decimal, Field(gt=0, decimal_places=2)] | None = None
    hasta: date | None = None

class SalarioPlusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    id: UUID
    tenant_id: UUID
    grupo: str
    rol: RolLiquidable
    descripcion: str
    monto: Decimal
    desde: date
    hasta: date | None
    created_at: datetime
    updated_at: datetime
```

---

## Router (`backend/app/api/v1/routers/grilla_salarial.py`)

Guard: `require_permission("grilla_salarial:operar")` en todos los endpoints.
Prefix: `/api/v1/grilla-salarial`
Tags: `["grilla-salarial"]`

```
# MateriaGrupo
GET    /materia-grupos              → list (query: materia_id?, grupo?)
POST   /materia-grupos             → create 201
GET    /materia-grupos/{id}        → get one
DELETE /materia-grupos/{id}        → soft delete 204

# SalarioBase
GET    /base                        → list (query: rol?)
POST   /base                        → create 201
GET    /base/{id}                   → get one
PATCH  /base/{id}                   → update (solo monto / hasta)
DELETE /base/{id}                   → soft delete 204

# SalarioPlus
GET    /plus                        → list (query: grupo?, rol?)
POST   /plus                        → create 201
GET    /plus/{id}                   → get one
PATCH  /plus/{id}                   → update (solo descripcion / monto / hasta)
DELETE /plus/{id}                   → soft delete 204
```

**Mapeo de errores del service:**
- `ValueError("solapamiento_vigencia")` → 409 `{"detail": "Ya existe un registro vigente para ese rol/período."}`
- `ValueError("not_found")` → 404
- `ValueError("materia_otro_tenant")` → 404 (no revelar existencia)

**Audit:** cada mutación exitosa genera:
```python
await audit_service.log(
    action=GRILLA_SALARIAL_OPERAR,
    actor_id=current_user.id,
    tenant_id=current_user.tenant_id,
    detalle={"tipo": "SalarioBase", "operacion": "create", "id": str(obj.id)},
    filas_afectadas=1,
)
```

---

## Tests (`backend/tests/test_grilla_salarial.py`)

Fixture: un tenant con usuario FINANZAS; un segundo tenant para aislamiento; Materia existente (prerequisito C-06).

### TestMateriaGrupo (~8 tests)
- `test_create_materia_grupo_ok` — POST 201, campos correctos
- `test_create_materia_grupo_duplicado_returns_409` — misma (materia, grupo) → 409
- `test_create_materia_grupo_misma_combinacion_otro_tenant_ok` — aislamiento
- `test_create_materia_grupo_materia_otro_tenant_returns_404`
- `test_list_materia_grupos_filtra_por_tenant`
- `test_list_por_grupo_filtra_correctamente`
- `test_delete_materia_grupo_soft` — 204; GET → 404; exists in DB
- `test_no_finanzas_returns_403` — COORDINADOR → 403

### TestSalarioBase (~10 tests)
- `test_create_base_ok` — POST 201, rol=PROFESOR, monto=Decimal("1500.00")
- `test_create_base_solapamiento_returns_409` — 2 bases para PROFESOR en mismo período
- `test_create_base_otro_rol_no_solapa` — TUTOR no interfiere con PROFESOR
- `test_find_vigente_por_periodo` — desde=2026-01-01, hasta=None → vigente en 2026-06
- `test_find_vigente_no_encontrado` — fecha antes de desde → None
- `test_update_base_monto_ok` — PATCH monto → 200
- `test_update_base_hasta_ok` — PATCH hasta → 200
- `test_delete_base_soft` — 204; GET → 404
- `test_monto_float_rechazado` — monto=1500.5 (float Python) debe llegar como Decimal
- `test_no_finanzas_returns_403`

### TestSalarioPlus (~8 tests)
- `test_create_plus_ok` — POST 201, grupo="PROG", rol=PROFESOR
- `test_create_plus_solapamiento_mismo_grupo_rol_returns_409`
- `test_create_plus_mismo_grupo_otro_rol_ok` — TUTOR no interfiere con PROFESOR
- `test_find_plus_vigente_para_periodo`
- `test_list_plus_filtra_por_grupo`
- `test_update_plus_monto_y_descripcion_ok`
- `test_delete_plus_soft`
- `test_no_finanzas_returns_403`
