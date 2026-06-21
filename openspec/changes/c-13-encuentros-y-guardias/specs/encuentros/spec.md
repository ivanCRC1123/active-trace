# Spec: Encuentros (F6.1–F6.5)

> Dependencias: C-07 ✓, C-05 ✓, C-06 ✓
> Governance: MEDIO
> Permiso: `encuentros:gestionar` (TUTOR=all, PROFESOR=own, COORDINADOR=all, ADMIN=all)

---

## Entidades

### SlotEncuentro (E9)

```
slot_encuentro:
  id              UUID PK
  tenant_id       UUID FK→tenant
  asignacion_id   UUID FK→asignacion       -- quién creó el slot
  materia_id      UUID FK→materia
  titulo          VARCHAR(255)
  hora            TIME
  dia_semana      VARCHAR(20) nullable      -- Lunes|Martes|...|Domingo (recurrente)
  fecha_inicio    DATE nullable             -- primer día de la serie (recurrente)
  cant_semanas    INTEGER DEFAULT 0         -- 0 = único
  fecha_unica     DATE nullable             -- modo único
  meet_url        TEXT nullable
  vig_desde       DATE nullable
  vig_hasta       DATE nullable
  created_at, updated_at, deleted_at
```

**Invariante de modo** (validado en service):
- Recurrente: `cant_semanas > 0 AND dia_semana NOT NULL AND fecha_inicio NOT NULL AND fecha_unica IS NULL`
- Único: `cant_semanas == 0 AND fecha_unica NOT NULL AND dia_semana IS NULL AND fecha_inicio IS NULL`

### InstanciaEncuentro (E10)

```
instancia_encuentro:
  id              UUID PK
  tenant_id       UUID FK→tenant
  slot_id         UUID FK→slot_encuentro nullable
  asignacion_id   UUID FK→asignacion       -- denormalizado de slot, para scoping
  materia_id      UUID FK→materia
  fecha           DATE
  hora            TIME
  titulo          VARCHAR(255)
  estado          VARCHAR(20)              -- Programado | Realizado | Cancelado
  meet_url        TEXT nullable
  video_url       TEXT nullable
  comentario      TEXT nullable
  created_at, updated_at, deleted_at
```

---

## Endpoints

### POST /api/v1/encuentros/slots
Crear slot y generar instancias.

**Request**: `SlotCreate`
```json
{
  "asignacion_id": "uuid",
  "materia_id": "uuid",
  "titulo": "Clase 1",
  "hora": "18:00",
  "modo": "recurrente",           // "recurrente" | "unico"
  "dia_semana": "Lunes",          // solo en recurrente
  "fecha_inicio": "2026-09-07",   // solo en recurrente
  "cant_semanas": 8,              // solo en recurrente
  "fecha_unica": null,            // solo en único
  "meet_url": "https://...",
  "vig_desde": "2026-09-01",
  "vig_hasta": "2026-12-01"
}
```

**Respuesta 201**: `SlotConInstanciasResponse` — slot + lista de instancias generadas.

**Errores**:
- 422 si fecha_inicio no cae en dia_semana (D-C13-1 opción A)
- 422 si modo=recurrente y cant_semanas=0
- 403 si PROFESOR y asignacion_id no pertenece al current_user
- 422 si cant_semanas > 52 (máximo razonable)

### GET /api/v1/encuentros/slots
Listar slots.

- PROFESOR: `WHERE asignacion_id IN (ids de sus asignaciones vigentes)`
- TUTOR/COORDINADOR/ADMIN: todos del tenant
- Query params: `?materia_id=`, `?activo_only=true`

**Respuesta 200**: `list[SlotResponse]`

### GET /api/v1/encuentros/slots/{slot_id}
Detalle slot con sus instancias.

- Verifica tenant scope (tenant_id del slot == tenant del JWT)
- PROFESOR(own): verifica que slot.asignacion pertenece al current_user
- **Respuesta 200**: `SlotConInstanciasResponse`
- 404 si no existe o fuera del tenant

### DELETE /api/v1/encuentros/slots/{slot_id}
Soft-delete del slot (cancela las instancias en estado Programado).

- Solo el propietario (PROFESOR) o COORDINADOR/ADMIN
- Las instancias Realizadas se conservan

### GET /api/v1/encuentros/instancias
Listar instancias (vista del usuario).

- PROFESOR(own): filtradas por sus asignaciones
- TUTOR/COORDINADOR/ADMIN: todas del tenant
- Query params: `?materia_id=`, `?estado=`, `?fecha_desde=`, `?fecha_hasta=`, `?slot_id=`
- Ordenadas por fecha ASC

**Respuesta 200**: `list[InstanciaResponse]`

### PATCH /api/v1/encuentros/instancias/{instancia_id}
Editar instancia (F6.3).

**Request**: `InstanciaUpdate` (todos los campos opcionales)
```json
{
  "estado": "Realizado",
  "meet_url": "https://...",
  "video_url": "https://...",
  "comentario": "Todo bien"
}
```

**Reglas**:
- PROFESOR(own): solo puede editar instancias de su propia asignación
- TUTOR: puede editar cualquier instancia (encuentros:gestionar=all)
- COORDINADOR/ADMIN: pueden editar cualquier instancia
- No se puede editar `fecha`, `hora`, `materia_id` (son del slot, inmutables en la instancia)
- Audit: `ENCUENTRO_EDITAR_INSTANCIA` con `{instancia_id, campos_modificados, nuevo_estado}`

**Respuesta 200**: `InstanciaResponse`

### GET /api/v1/encuentros/fragmento-lms
Fragmento Markdown con encuentros para publicar en el LMS (F6.4).

Query params: `?materia_id=UUID` (obligatorio), `?slot_id=UUID` (opcional, filtra a un slot)

**Respuesta 200**:
```json
{ "fragmento": "## Encuentros — Programación I\n\n### Programados\n- **Lun 07-Sep-2026...**" }
```

Incluye:
- `Programado`: fecha + hora + titulo + meet_url (si la tiene)
- `Realizado`: fecha + hora + titulo + video_url (si la tiene)
- Excluye: `Cancelado`
- Orden: fecha ASC

---

## Schemas Pydantic

```python
class SlotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asignacion_id: UUID
    materia_id: UUID
    titulo: str
    hora: time
    modo: Literal["recurrente", "unico"]
    dia_semana: str | None = None      # Lunes..Domingo
    fecha_inicio: date | None = None
    cant_semanas: int | None = None
    fecha_unica: date | None = None
    meet_url: str | None = None
    vig_desde: date | None = None
    vig_hasta: date | None = None

class InstanciaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado: Literal["Programado", "Realizado", "Cancelado"] | None = None
    meet_url: str | None = None
    video_url: str | None = None
    comentario: str | None = None

class InstanciaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    slot_id: UUID | None
    asignacion_id: UUID
    materia_id: UUID
    fecha: date
    hora: time
    titulo: str
    estado: str
    meet_url: str | None
    video_url: str | None
    comentario: str | None
    created_at: datetime
    updated_at: datetime

class SlotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    asignacion_id: UUID
    materia_id: UUID
    titulo: str
    hora: time
    modo: str               # "recurrente" | "unico" (derivado de cant_semanas)
    dia_semana: str | None
    fecha_inicio: date | None
    cant_semanas: int
    fecha_unica: date | None
    meet_url: str | None
    vig_desde: date | None
    vig_hasta: date | None
    created_at: datetime

class SlotConInstanciasResponse(SlotResponse):
    model_config = ConfigDict(extra="forbid")
    instancias: list[InstanciaResponse]
```

---

## EncuentroService — interfaz

```python
class EncuentroService:
    async def crear_slot(current_user, data: SlotCreate) -> SlotConInstanciasResponse
    async def listar_slots(current_user, materia_id=None) -> list[SlotResponse]
    async def get_slot(current_user, slot_id) -> SlotConInstanciasResponse   # 403/404
    async def eliminar_slot(current_user, slot_id) -> bool
    async def listar_instancias(current_user, filtros) -> list[InstanciaResponse]
    async def editar_instancia(current_user, instancia_id, data: InstanciaUpdate) -> InstanciaResponse
    async def fragmento_lms(current_user, materia_id, slot_id=None) -> str
```

**_assert_propietario_o_admin(current_user, asignacion_id)**:
```
Si current_user tiene `encuentros:gestionar` = "all" → pasa
Si tiene "own" → verificar slot.asignacion_id in [ids de asignaciones vigentes del usuario]
Si no pasa → raise PermissionError
```

---

## Audit codes a agregar

```python
ENCUENTRO_CREAR = "ENCUENTRO_CREAR"
ENCUENTRO_EDITAR_INSTANCIA = "ENCUENTRO_EDITAR_INSTANCIA"
```

Detalle del audit:
- `ENCUENTRO_CREAR`: `{slot_id, materia_id, modo, instancias_generadas: N}`
- `ENCUENTRO_EDITAR_INSTANCIA`: `{instancia_id, campos_modificados: [...], nuevo_estado}`

---

## Escenarios de test

### TestSlotCrearRecurrente
- Crear slot recurrente con `cant_semanas=4` → 4 instancias generadas con fechas correctas
- Verificar que instancia[0].fecha == fecha_inicio
- Verificar que instancia[i].fecha == fecha_inicio + 7*i días
- Crear slot con `fecha_inicio` que no cae en `dia_semana` → 422
- PROFESOR crea con `asignacion_id` ajena → 403
- Sin auth → 401

### TestSlotCrearUnico
- Crear slot único con `fecha_unica` → 1 instancia en esa fecha exacta
- Crear slot único con `cant_semanas > 0` → 422 (modo inválido)

### TestListarInstancias
- PROFESOR solo ve instancias de sus asignaciones (not otras)
- COORDINADOR ve todas las instancias del tenant
- Filtro por estado y materia funciona

### TestEditarInstancia
- PATCH `estado=Realizado` → 200, audit generado con `nuevo_estado`
- PATCH `video_url` → 200 (sin restricción de estado)
- PROFESOR edita instancia propia → 200
- PROFESOR edita instancia ajena → 403
- TUTOR edita instancia ajena → 200 (scope=all)
- Intentar editar campo inmutable (`fecha`) → 422 (extra='forbid')
- Sin auth → 401

### TestFragmentoLMS
- Retorna Programados con meet_url
- Retorna Realizados con video_url
- No incluye Cancelados
- Resultado vacío si no hay instancias → fragmento vacío

### TestTenantIsolation
- Slot de tenant A invisible para usuario de tenant B
