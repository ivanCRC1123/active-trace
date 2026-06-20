# C-15 — `avisos-y-acknowledgment` — Design

## Context

C-07 estableció `Usuario` y `Asignacion`. C-09 estableció `EntradaPadron` (alumnos por
cohorte). C-15 agrega el tablón de avisos institucional: publicación segmentada (Global /
PorMateria / PorCohorte / PorRol), ventana de vigencia y acuse de recibo.

Fuentes: `knowledge-base/04_modelo_de_datos.md` §E13; `knowledge-base/05_reglas_de_negocio.md`
RN-18/RN-19/RN-20; `knowledge-base/06_funcionalidades.md` F3.5;
`knowledge-base/07_flujos_principales.md` FL-09.

## Goals / Non-Goals

**Goals:**
- 2 modelos ORM (Aviso, AcknowledgmentAviso) con soft-delete y tenant-scope.
- CRUD de avisos gestionado por COORDINADOR/ADMIN (`avisos:publicar`).
- Endpoint `mis-avisos` que aplica RN-18 (vigencia) + RN-20 (scope) + exclusión de acked.
- Ack idempotente por usuario (`comunicacion:confirmar_aviso`), disponible para todos los roles.
- Stats derivadas (sin denormalización).
- Sin cambios de permisos: reutilizar los ya sembrados desde C-04.
- ~25 tests TDD cubriendo CRUD, filtrado de scope, ventana de vigencia, ack y RBAC.

**Non-Goals:**
- Push/notificación en tiempo real al usuario cuando se publica un aviso (fuera de scope).
- Integración con el worker de comunicaciones de C-12 (avisos son in-app, no por email).
- Historial de versionado del contenido de un aviso (solo se edita el registro actual).

## Decisions

### D1 — ENUMs Postgres: `alcance_aviso` y `severidad_aviso`

```python
class AlcanceAviso(str, enum.Enum):
    Global     = "Global"
    PorMateria = "PorMateria"
    PorCohorte = "PorCohorte"
    PorRol     = "PorRol"

class SeveridadAviso(str, enum.Enum):
    Info        = "Info"
    Advertencia = "Advertencia"
    Critico     = "Critico"   # sin tilde — safe for Postgres enum names
```

Ambos ENUMs se crean en la migración 013 con `checkfirst=True` en el `upgrade()`.
El `downgrade()` los elimina con `checkfirst=True`.

### D2 — `rol_destino` como String(50) nullable (sin nuevo ENUM de rol)

El KB define `rol_destino` como un enum de roles. Sin embargo, crear un ENUM Postgres
`rol_sistema` en la migración 013 acoplaría este change a la definición de roles de C-03/C-04.

Decisión: almacenar `rol_destino` como `String(50)` nullable. Los valores válidos son
`ALUMNO | TUTOR | PROFESOR | COORDINADOR | NEXO | ADMIN | FINANZAS`. La validación se hace
en el schema Pydantic (via `Literal`), no en el ENUM de BD.

Esto permite agregar roles futuros sin migración de ENUM y evita dependencia cross-change.

### D3 — `AcknowledgmentAviso` usa BaseEntityMixin; `created_at` actúa como `confirmado_at`

`AcknowledgmentAviso` hereda `BaseEntityMixin` (id, tenant_id, created_at, updated_at,
deleted_at) por consistencia con el resto del codebase. El campo `confirmado_at` del KB
queda cubierto por `created_at`.

El response schema expone `confirmado_at` como alias de `created_at` usando
`Field(alias="created_at")` o directamente renombrándolo en el modelo de respuesta.

Unicidad: `UniqueConstraint("tenant_id", "aviso_id", "usuario_id", name="uq_ack_aviso_usuario")`.
La idempotencia se gestiona en el servicio (get-or-create), NO con INSERT ON CONFLICT
(para mantener el patrón uniforme del codebase).

### D4 — Filtrado de audiencia: el servicio resuelve el contexto del usuario

`AvisosService.mis_avisos(*, tenant_id, current_user, now)` resuelve en dos pasos:

**Paso 1 — Contexto del usuario (vía repositories existentes):**

```python
# Roles y contextos del usuario via Asignacion
asignaciones = await AsignacionRepository(session, tenant_id).list_activas_by_usuario(user_id)
roles    = {a.rol for a in asignaciones}
materias = {a.materia_id for a in asignaciones if a.materia_id}
cohortes = {a.cohorte_id for a in asignaciones if a.cohorte_id}

# Para ALUMNOs: cohortes via EntradaPadron (asignaciones puede estar vacío)
if not cohortes:
    entradas = await EntradaPadronRepository(session, tenant_id).list_activas_by_usuario(user_id)
    cohortes = {e.version.cohorte_id for e in entradas}
```

**Paso 2 — Query filtrada en el repositorio:**

```python
await AvisoRepository(session, tenant_id).list_visibles_para_usuario(
    roles=roles,
    materias=materias,
    cohortes=cohortes,
    usuario_id=user_id,
    now=now,
)
```

El método `list_visibles_para_usuario` aplica **tres capas de filtro**:

**RN-18 (vigencia) — SIEMPRE aplicada** como parte del filtro base:
```python
Aviso.inicio_en <= now,   # RN-18: no mostrar antes del inicio
Aviso.fin_en >= now,      # RN-18: no mostrar después del fin
```
Esto garantiza que avisos fuera de su ventana temporal nunca se devuelven,
independientemente del scope o del ack.

**RN-20 (scope) — OR compuesto:**

```python
scope_filter = or_(
    Aviso.alcance == AlcanceAviso.Global,
    and_(Aviso.alcance == AlcanceAviso.PorRol,     Aviso.rol_destino.in_(roles)),
    and_(Aviso.alcance == AlcanceAviso.PorMateria,  Aviso.materia_id.in_(materias)),
    and_(Aviso.alcance == AlcanceAviso.PorCohorte,  Aviso.cohorte_id.in_(cohortes)),
)

# Excluir avisos ya acked cuando requiere_ack = True
acked_sub = (
    select(AcknowledgmentAviso.aviso_id)
    .where(
        AcknowledgmentAviso.usuario_id == usuario_id,
        AcknowledgmentAviso.tenant_id == tenant_id,
        AcknowledgmentAviso.deleted_at.is_(None),
    )
)
ack_filter = or_(
    Aviso.requiere_ack == False,
    Aviso.id.not_in(acked_sub),
)

stmt = (
    select(Aviso)
    .where(
        Aviso.tenant_id == tenant_id,
        Aviso.activo == True,
        Aviso.deleted_at.is_(None),
        Aviso.inicio_en <= now,
        Aviso.fin_en >= now,
        scope_filter,
        ack_filter,
    )
    .order_by(Aviso.orden.asc(), Aviso.inicio_en.desc())
)
```

**Caso borde — sin contexto (listas vacías)**: si el usuario no tiene asignaciones ni
entradas de padrón activas, solo los avisos `Global` son visibles. Los filtros
`PorRol`, `PorMateria`, `PorCohorte` no generarán resultados (IN lista vacía → False en SQL).

### D5 — Validaciones de negocio en AvisosService.create_aviso

```
if alcance == PorMateria  → materia_id required, cohorte_id debe ser None
if alcance == PorCohorte  → cohorte_id required, materia_id debe ser None
if alcance == PorRol      → rol_destino required
if alcance == Global      → materia_id, cohorte_id, rol_destino deben ser None

fin_en > inicio_en         → ValueError si no se cumple
materia_id pertenece al tenant → si no, ValueError("materia not found")
cohorte_id pertenece al tenant → si no, ValueError("cohorte not found")
```

Las validaciones de materia_id/cohorte_id usan los mismos repository calls que C-14/C-17.

### D6 — Router con dos conjuntos de endpoints

```
/api/v1/avisos                         ← avisos:publicar (COORDINADOR/ADMIN)
  GET   /                              listado admin (todo, sin filtro de vigencia)
  POST  /              → 201           crear aviso
  GET   /mis-avisos                    ← comunicacion:confirmar_aviso (TODOS los roles)
  GET   /{id}                          ← avisos:publicar
  PATCH /{id}                          ← avisos:publicar
  DELETE /{id}         → 204           ← avisos:publicar (soft delete)
  GET   /{id}/stats                    ← avisos:publicar (total confirmaciones)
  POST  /{id}/ack      → 201/200       ← comunicacion:confirmar_aviso (TODOS los roles)
```

**Regla de orden en el router**: `GET /mis-avisos` DEBE registrarse ANTES de `GET /{id}` para
evitar que FastAPI interprete "mis-avisos" como un UUID y devuelva 422. (Mismo patrón que
`/metricas-panel` en C-14.)

### D7 — Audit codes: AVISO_CREAR y AVISO_ACK

```python
# En backend/app/core/audit_codes.py, sección # C-15
AVISO_CREAR = "AVISO_CREAR"
AVISO_ACK   = "AVISO_ACK"
```

`AVISO_CREAR` se registra en `create_aviso` con `detalle={"alcance": ..., "titulo": ...}`.
`AVISO_ACK` se registra en `confirmar_aviso` con `detalle={"aviso_id": ..., "idempotente": bool}`.

No se auditan las otras operaciones CRUD (update/delete) para no sobre-auditar, dado que el
change CHANGES.md de C-15 no las menciona en "Tests: filtrado por scope... ack (deja de
mostrarse + cuenta), orden de prioridad". Si el negocio lo requiere, se agrega sin migración.

### D8 — Soft-delete en ambas tablas; AcknowledgmentAviso en práctica es append-only

`Aviso` tiene soft-delete estándar: `DELETE /{id}` setea `deleted_at`.
`AcknowledgmentAviso` hereda `deleted_at` via BaseEntityMixin pero no se utiliza en la práctica
(un ack no se deshace). El soft-delete está disponible si el negocio lo requiere sin migración.

### D9 — Stats: solo `confirmaciones`, sin `total_alcanzados`

Calcular `total_alcanzados` requiere cruzar `alcance/rol_destino/materia_id/cohorte_id`
con todos los usuarios del tenant — una query O(N usuarios). Se descarta por rendimiento.

`GET /{id}/stats` devuelve únicamente `{ confirmaciones: int }`:
```sql
SELECT COUNT(*) FROM acknowledgment_aviso
WHERE aviso_id = :id AND deleted_at IS NULL
```

Si el negocio requiere `total_alcanzados`, se agrega como campo calculado bajo demanda con
un endpoint propio y sin cambio de modelo.

## Migration Plan

- Revision: `d4e5f6a7b8c9`
- Down revision: `b1c2d3e4f5a6` (012 — C-14)
- `upgrade()`:
  1. `sa.Enum("Global","PorMateria","PorCohorte","PorRol", name="alcance_aviso").create(op.get_bind(), checkfirst=True)`
  2. `sa.Enum("Info","Advertencia","Critico", name="severidad_aviso").create(op.get_bind(), checkfirst=True)`
  3. `op.create_table("aviso", ...)` — BaseEntityMixin + alcance, materia_id (nullable), cohorte_id (nullable), rol_destino String(50) (nullable), severidad, titulo, cuerpo, inicio_en, fin_en, orden, activo, requiere_ack; FKs RESTRICT nullable; índices
  4. `op.create_table("acknowledgment_aviso", ...)` — BaseEntityMixin + aviso_id, usuario_id; FKs RESTRICT; UniqueConstraint
- `downgrade()`:
  1. Drop `acknowledgment_aviso`, luego `aviso`
  2. `sa.Enum(name="severidad_aviso").drop(op.get_bind(), checkfirst=True)`
  3. `sa.Enum(name="alcance_aviso").drop(op.get_bind(), checkfirst=True)`

## Risks / Trade-offs

- **Contexto de usuario para scope**: para ALUMNOs sin asignaciones, el servicio cae al
  fallback de EntradaPadron. Si un alumno no tiene EntradaPadron activo, solo ve avisos Global.
  Esto es correcto por diseño: un alumno sin padrón activo no está matriculado.
- **`fil_en` requerido**: no se soportan avisos sin fecha de fin ("vigentes indefinidamente").
  Obliga al publicador a poner una fecha de fin. Trade-off aceptable: simplifica la query y
  evita avisos "eternos" por descuido. Si el negocio lo necesita, se hace nullable con default
  `datetime.max` sin cambio de schema.
- **Sin cache en scope resolution**: cada llamada a `mis-avisos` ejecuta 2-3 queries (asignaciones
  + padron + avisos). Bajo carga alta esto puede ser costoso. Mitigación futura: cachear
  contexto del usuario en Redis por TTL corto. Por ahora el costo es aceptable (misma
  magnitud que `mis-comunicaciones` de C-12).
- **Roles como String**: sin ENUM de BD para `rol_destino`. La coherencia se mantiene en el
  schema Pydantic. Si se agrega un rol nuevo, no hay migración de ENUM, pero hay que actualizar
  el `Literal` del schema.
