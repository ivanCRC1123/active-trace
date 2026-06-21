# Spec: Guardias (F6.6)

> Governance: MEDIO
> Permisos:
>   - `guardias:registrar` = "own" → TUTOR, PROFESOR (registran sus propias guardias)
>   - `guardias:registrar` = "all" → COORDINADOR, ADMIN (consulta y export global)

---

## Entidad (E11 + D-C13-6 extensión)

```
guardia:
  id              UUID PK
  tenant_id       UUID FK→tenant
  asignacion_id   UUID FK→asignacion       -- quién cubre la guardia
  materia_id      UUID FK→materia
  carrera_id      UUID FK→carrera
  cohorte_id      UUID FK→cohorte
  dia             VARCHAR(20)              -- Lunes|Martes|...|Domingo (E11)
  fecha           DATE nullable            -- fecha específica [D-C13-6 opción A]
  horario         VARCHAR(50)              -- "14:00–14:45"
  estado          VARCHAR(20)              -- Pendiente | Realizada | Cancelada
  comentarios     TEXT nullable
  created_at, updated_at, deleted_at      -- BaseEntityMixin (D-C13-8)
```

**Nota D-C13-6**: si se confirma Opción A (agregar `fecha`), el campo `dia` se puede derivar de `fecha.strftime('%A')` en español, pero se almacena separado para indexar por día de la semana sin parsear la fecha.

---

## Endpoints

### POST /api/v1/guardias
Registrar guardia.

**Permiso**: `guardias:registrar` (any scope — el service enforcea "own")

**Request**: `GuardiaCreate`
```json
{
  "asignacion_id": "uuid",
  "materia_id": "uuid",
  "carrera_id": "uuid",
  "cohorte_id": "uuid",
  "dia": "Martes",
  "fecha": "2026-09-08",       // nullable si D-C13-6 NO aprobado
  "horario": "14:00–14:45",
  "comentarios": "Sin novedades"
}
```

**Reglas**:
- `asignacion_id` DEBE pertenecer al `current_user` (propio). Sin excepciones — no hay forma de registrar guardia de otro usuario.
- `estado` inicial siempre `Pendiente` (lo impone el service, no el request body).
- COORDINADOR/ADMIN que tienen `all` también pueden registrar: en ese caso `asignacion_id` es libre (pueden registrar en nombre de alguien si son propietarios de esa asignacion, o si el negocio lo requiere).

**Respuesta 201**: `GuardiaResponse`

**Errores**:
- 403 si `asignacion_id` no pertenece al `current_user` y el permiso es "own"
- 422 si `asignacion_id` no existe en el tenant

### GET /api/v1/guardias
Listar guardias.

**Scoping**:
- TUTOR/PROFESOR (own): `WHERE asignacion_id IN (ids propios)`
- COORDINADOR/ADMIN (all): todo el tenant

**Query params**: `?materia_id=`, `?carrera_id=`, `?cohorte_id=`, `?estado=`, `?fecha_desde=`, `?fecha_hasta=`, `?asignacion_id=` (solo para COORDINADOR/ADMIN)

**Respuesta 200**: `list[GuardiaResponse]`

### PATCH /api/v1/guardias/{guardia_id}
Editar guardia (estado, comentarios).

**Request**: `GuardiaUpdate`
```json
{
  "estado": "Realizada",
  "comentarios": "Se cubrió con 3 alumnos"
}
```

**Reglas**:
- TUTOR/PROFESOR(own): solo su propia guardia
- COORDINADOR/ADMIN: cualquier guardia del tenant
- Campos editables: `estado`, `comentarios`, `horario`, `fecha`
- `asignacion_id`, `materia_id`, `carrera_id`, `cohorte_id` no modificables (FK scoping)

**Respuesta 200**: `GuardiaResponse`

### GET /api/v1/guardias/export
Exportar guardias (F6.6: "exportación del registro").

**Permiso**: `guardias:registrar=all` solo (COORDINADOR/ADMIN)

Query params: mismos filtros que GET /api/v1/guardias

**Respuesta 200**: `Content-Type: text/csv`
```
asignacion_id,docente_nombre,docente_apellidos,materia,carrera,cohorte,dia,fecha,horario,estado,comentarios,creada_at
```

---

## Schemas Pydantic

```python
class GuardiaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asignacion_id: UUID
    materia_id: UUID
    carrera_id: UUID
    cohorte_id: UUID
    dia: str                           # Lunes|Martes|...|Domingo
    fecha: date | None = None          # D-C13-6 — null si no se aprueba Opción A
    horario: str
    comentarios: str | None = None

class GuardiaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado: Literal["Pendiente", "Realizada", "Cancelada"] | None = None
    comentarios: str | None = None
    horario: str | None = None
    fecha: date | None = None

class GuardiaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    asignacion_id: UUID
    materia_id: UUID
    carrera_id: UUID
    cohorte_id: UUID
    dia: str
    fecha: date | None
    horario: str
    estado: str
    comentarios: str | None
    created_at: datetime
    updated_at: datetime
```

---

## GuardiaService — interfaz

```python
class GuardiaService:
    async def registrar(current_user, data: GuardiaCreate) -> GuardiaResponse
    async def listar(current_user, filtros) -> list[GuardiaResponse]
    async def editar(current_user, guardia_id, data: GuardiaUpdate) -> GuardiaResponse
    async def exportar_csv(current_user, filtros) -> str   # CSV string
```

**_assert_propietario_o_admin(current_user, guardia)**:
```
permission_scope = get_permission_scope(current_user, "guardias:registrar")
Si scope == "all" → pasa
Si scope == "own" → verificar guardia.asignacion_id in [ids asignaciones vigentes del usuario]
Si no → raise PermissionError
```

---

## Audit codes

```python
GUARDIA_REGISTRAR = "GUARDIA_REGISTRAR"
```

Detalle: `{guardia_id, materia_id, asignacion_id, estado_inicial: "Pendiente"}`

---

## Escenarios de test

### TestGuardiaRegistrar
- TUTOR registra guardia con su asignacion_id → 201, estado=Pendiente
- TUTOR registra guardia con asignacion_id ajena → 403
- PROFESOR registra guardia propia → 201
- COORDINADOR registra guardia (any asignacion del tenant) → 201
- Sin auth → 401
- 422 si asignacion_id no existe en tenant

### TestGuardiaListar
- TUTOR solo ve sus propias guardias (no las de otro tutor)
- COORDINADOR ve guardias de todos en el tenant
- Filtro por materia y estado funciona
- Filtro por fecha_desde/fecha_hasta (si D-C13-6 aprobado)

### TestGuardiaEditar
- TUTOR edita propia → 200, estado actualizado
- TUTOR edita ajena → 403
- COORDINADOR edita cualquier guardia → 200
- Intentar modificar materia_id → 422 (extra='forbid')

### TestGuardiaExport
- COORDINADOR exporta → 200 con CSV
- TUTOR intenta exportar → 403

### TestGuardiaTenantIsolation
- Guardia de tenant A invisible para COORDINADOR de tenant B

### TestGuardiaEstado
- Estado inicial es siempre Pendiente (ignorar si body lo envía diferente)
- Transición Pendiente → Realizada válida
- Transición Pendiente → Cancelada válida
