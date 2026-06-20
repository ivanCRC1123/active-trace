# Spec: VersionPadron (E6 — encabezado de padrón)

## Entidad

Registra una carga de padrón de alumnos para una combinación `(materia_id, cohorte_id)`.
Solo una instancia puede estar `activa = True` por `(tenant_id, materia_id, cohorte_id)` en cualquier momento.

## Campos

| Campo | Tipo DB | Nullable | Notas |
|-------|---------|----------|-------|
| id | UUID PK | no | gen_random_uuid() |
| tenant_id | UUID FK→tenant | no | CASCADE |
| materia_id | UUID FK→materia | no | RESTRICT |
| cohorte_id | UUID FK→cohorte | no | RESTRICT |
| cargado_por | UUID FK→user | no | RESTRICT — usuario que realizó la carga |
| cargado_at | TIMESTAMPTZ | no | DEFAULT now() |
| activa | BOOLEAN | no | DEFAULT TRUE — solo una puede ser TRUE por (tenant, materia, cohorte) |
| created_at | TIMESTAMPTZ | no | |
| updated_at | TIMESTAMPTZ | no | trigger ON UPDATE |
| deleted_at | TIMESTAMPTZ | yes | NULL = no borrada |

## Constraints de DB

```sql
-- Unicidad de versión activa (parcial) — ver D-C09-1
CREATE UNIQUE INDEX uq_version_padron_activa
  ON version_padron (tenant_id, materia_id, cohorte_id)
  WHERE activa = TRUE AND deleted_at IS NULL;
```

## Invariantes de negocio

- Al crear una nueva VersionPadron `activa=True`, la versión activa anterior del mismo
  `(tenant_id, materia_id, cohorte_id)` se pone a `activa=False` en la misma transacción.
- `cargado_por` debe pertenecer al mismo `tenant_id`.
- `materia_id` y `cohorte_id` deben existir y pertenecer al mismo `tenant_id`.
- La creación de VersionPadron es el trigger del evento de auditoría `PADRON_CARGAR`.

## Modelo SQLAlchemy

```python
class VersionPadron(Base, BaseEntityMixin):
    __tablename__ = "version_padron"

    materia_id: Mapped[UUID] = mapped_column(ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False)
    cohorte_id: Mapped[UUID] = mapped_column(ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=False)
    cargado_por: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    cargado_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

## VersionPadronRepository

Métodos requeridos:
- `get_active(materia_id, cohorte_id) → VersionPadron | None`
- `deactivate_current(materia_id, cohorte_id) → None` — UPDATE activa=False en la misma sesión
- `list_by_materia(materia_id) → Sequence[VersionPadron]` — todas las versiones (historial)

## VersionPadronResponse schema

```python
class VersionPadronResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    tenant_id: UUID
    materia_id: UUID
    cohorte_id: UUID
    cargado_por: UUID
    cargado_at: datetime
    activa: bool
    total_entradas: int        # inyectado por service (COUNT de EntradaPadron)
    entradas_vinculadas: int   # inyectado por service (COUNT WHERE usuario_id IS NOT NULL)
    created_at: datetime
    updated_at: datetime
```

## PadronImportResult schema (response de import exitoso)

```python
class PadronImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: VersionPadronResponse
    total_importadas: int
    entradas_vinculadas: int   # auto-linked a Usuario existente
    advertencias: list[str]    # filas descartadas o con datos parciales
```

## PadronPreview schema (response de preview=true)

```python
class PadronPreviewEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str
    apellidos: str
    comision: str | None
    regional: str | None
    vinculado: bool            # True si email_hash coincide con User existente

class PadronPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    vinculados: int
    advertencias: list[str]
    entradas: list[PadronPreviewEntry]
```

## Escenarios

### Import exitoso (archivo)
```
DADO que el COORDINADOR está autenticado en TENANT-A
Y existe materia {mid} y cohorte {cid} en ese tenant
Y NO hay versión activa previa
CUANDO POST /api/v1/padron/{mid}/cohortes/{cid}/importar con archivo de 25 alumnos
ENTONCES 201 con PadronImportResult.total_importadas=25
Y version_padron tiene 1 fila con activa=True
```

### Import desactiva versión anterior
```
DADO que existe VersionPadron activa V1 para (mid, cid)
CUANDO POST /api/v1/padron/{mid}/cohortes/{cid}/importar con nuevo archivo
ENTONCES se crea V2 con activa=True
Y V1 tiene activa=False (no deleted_at — sigue en historial)
Y el índice uq_version_padron_activa no viola unicidad
```

### Preview no escribe en DB
```
CUANDO POST /api/v1/padron/{mid}/cohortes/{cid}/importar?preview=true con archivo
ENTONCES 200 PadronPreview
Y version_padron NO tiene nuevas filas
Y entrada_padron NO tiene nuevas filas
```

### Vaciar — PROFESOR solo puede vaciar sus propias cargas
```
DADO que la versión activa fue cargada por USUARIO-B (otro PROFESOR)
Y el usuario autenticado es USUARIO-A (PROFESOR)
CUANDO DELETE /api/v1/padron/{mid}/cohortes/{cid}/vaciar
ENTONCES 403 Forbidden "no tenés permiso para vaciar versiones cargadas por otros usuarios"
```

### Vaciar — COORDINADOR puede vaciar cualquier versión
```
DADO que la versión activa fue cargada por cualquier usuario
Y el usuario autenticado es COORDINADOR (scope=all)
CUANDO DELETE /api/v1/padron/{mid}/cohortes/{cid}/vaciar
ENTONCES 204 No Content
Y VersionPadron tiene activa=False y deleted_at ≠ NULL
Y EntradaPadron permanece en DB (solo la versión se soft-deletes)
```

### GET sin versión activa
```
CUANDO GET /api/v1/padron/{mid}/cohortes/{cid}
Y no existe VersionPadron activa para ese (mid, cid)
ENTONCES 404 "no hay padrón activo para esta materia y cohorte"
```
