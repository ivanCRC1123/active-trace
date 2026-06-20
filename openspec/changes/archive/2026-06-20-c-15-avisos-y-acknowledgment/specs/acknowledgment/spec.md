# Spec — AcknowledgmentAviso + endpoints de consumo

## Modelo ORM (`backend/app/models/aviso.py`, misma clase)

```python
class AcknowledgmentAviso(Base, BaseEntityMixin):
    __tablename__ = "acknowledgment_aviso"

    aviso_id:   Mapped[UUID]   # FK → aviso.id RESTRICT, nullable=False, index=True
    usuario_id: Mapped[UUID]   # FK → user.id RESTRICT, nullable=False, index=True
    # created_at de BaseEntityMixin actúa como confirmado_at

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "aviso_id", "usuario_id",
                            name="uq_ack_aviso_usuario"),
        sa.Index("idx_ack_aviso_id", "aviso_id"),
        sa.Index("idx_ack_usuario_id", "tenant_id", "usuario_id"),
    )
```

## Schemas

**`AckAvisoResponse`** (`from_attributes=True`):
```python
id:           UUID
aviso_id:     UUID
usuario_id:   UUID
confirmado_at: datetime  # serializa created_at
```

**`MisAvisosResponse`** (lista):
```python
# Reutiliza AvisoResponse, sin campos adicionales.
# El filtrado de scope/vigencia/ack se hace en el servicio; el schema no lo refleja.
```

## Repositorio (`AckAvisoRepository`)

```python
class AckAvisoRepository(BaseRepository[AcknowledgmentAviso]):
    model_class = AcknowledgmentAviso

    async def get_by_aviso_usuario(
        self, aviso_id: UUID, usuario_id: UUID
    ) -> AcknowledgmentAviso | None:
        # SELECT WHERE aviso_id=:aviso_id AND usuario_id=:usuario_id
        # AND tenant_id=:tenant_id AND deleted_at IS NULL

    async def create_ack(
        self, aviso_id: UUID, usuario_id: UUID
    ) -> AcknowledgmentAviso:
        # INSERT con tenant_id, aviso_id, usuario_id
```

## Nota: "vistas" = acks en esta entrega

KB E13 menciona contadores de "vistas y confirmaciones" derivados de `AcknowledgmentAviso`.
Sin embargo, `AcknowledgmentAviso` solo registra el acuse de recibo explícito (click de
confirmación), NO impresiones de pantalla (vistas sin acción). En esta entrega:
- **vistas** = confirmaciones = COUNT(AcknowledgmentAviso) para el aviso.
- No hay tracking separado de impresiones.
- `GET /{id}/stats` expone `{ confirmaciones: int }` sin campo `vistas`.
- Si el negocio requiere tracking de impresiones en el futuro, se agrega una tabla
  `VistaAviso` sin cambiar el modelo actual.

## Servicio (`AvisosService`, métodos de ack y mis-avisos)

```python
async def mis_avisos(
    self, *, tenant_id: UUID, current_user: CurrentUser, now: datetime
) -> list[Aviso]:
    # 1. Resolver contexto: AsignacionRepository.list_activas_by_usuario + EntradaPadron
    # 2. AvisoRepository.list_visibles_para_usuario(roles, materias, cohortes, usuario_id, now)

async def confirmar_aviso(
    self, *, tenant_id: UUID, aviso_id: UUID, current_user: CurrentUser
) -> tuple[AcknowledgmentAviso, bool]:
    # Verifica que el aviso exista en el tenant → ValueError("not found")
    # get_by_aviso_usuario: si existe → return (existing, False)  [idempotente]
    # si no existe → create_ack + AuditService.log(AVISO_ACK, ...) → return (ack, True)
    # El router usa el bool para emitir 200 (ya existía) o 201 (nuevo)
```

## Endpoints de consumo (`comunicacion:confirmar_aviso`)

| Método | Ruta | Status | Descripción |
|--------|------|--------|-------------|
| `GET`  | `/api/v1/avisos/mis-avisos` | 200 | Lista avisos visibles para el usuario (RN-18+RN-20+acked) |
| `POST` | `/api/v1/avisos/{id}/ack`  | 201/200 | Confirmar aviso; 201=nuevo, 200=ya confirmado |

### Regla de orden crítica en el router

```python
router = APIRouter(prefix="/api/v1/avisos", tags=["avisos"])

# Endpoints con comunicacion:confirmar_aviso — DEBEN ir ANTES de /{id}
@router.get("/mis-avisos", ...)          # ← PRIMERO
@router.post("/{id}/ack", ...)           # ← OK (el path collision no aplica aquí)

# Endpoints con avisos:publicar
@router.get("/", ...)
@router.post("/", ...)
@router.get("/{id}", ...)               # ← DESPUÉS de /mis-avisos
@router.patch("/{id}", ...)
@router.delete("/{id}", ...)
@router.get("/{id}/stats", ...)
```

### Mapeo ValueError → HTTPException para endpoints de consumo

| ValueError message | Status | Detail |
|--------------------|--------|--------|
| `"not found"` | 404 | aviso no existe en el tenant |

### Comportamiento de `POST /{id}/ack`

1. Servicio verifica aviso en tenant → 404 si no existe.
2. Si ya existe AcknowledgmentAviso para `(aviso_id, usuario_id)` → devuelve `(existing, False)`.
3. Si no existe → crea AcknowledgmentAviso + audit AVISO_ACK → devuelve `(ack, True)`.
4. Router: `created=True` → `status_code=201`; `created=False` → `status_code=200`.

## conftest.py — cleanup requerido

Agregar al autouse `_clean_padron_tables` ANTES de las tablas que `aviso` referencia (materia, cohorte):

```python
await db_session.execute(text("DELETE FROM acknowledgment_aviso"))
await db_session.execute(text("DELETE FROM aviso"))
# ... tablas existentes ...
```
