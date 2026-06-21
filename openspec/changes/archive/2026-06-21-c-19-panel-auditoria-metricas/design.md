# C-19 — `panel-auditoria-metricas` — Design

> Este documento surfacea explícitamente las 6 decisiones de diseño que el implementador **no debe resolver en silencio**.

---

## Arquitectura general

Clean Architecture, solo lectura:

```
Router (GET) → require_permission("auditoria:ver", scoped=True)
     ↓
AuditoriaService   — aplica scoping de RBAC, orquesta repos
     ↓          ↘
AuditoriaRepository    ComunicacionRepository.estado_por_docente()
  (queries de panel     (método nuevo, repo existente de C-12)
   sobre audit_log)
```

- **No hay escritura** en ninguna capa: cero `INSERT`, `UPDATE`, `DELETE`.
- **No se audita la lectura**: los endpoints de panel y log no llaman a `AuditLogRepository.insert()`. Consistente con el resto de los endpoints GET del sistema.
- **No hay entidad nueva ni migración Alembic**: `audit_log` (C-05) y `comunicacion` (C-12) ya tienen todos los campos necesarios.

---

## Decisión 1 — Sin migración, sin entidad nueva

`AuditLog` (E-AUD, C-05) contiene: `id`, `tenant_id`, `fecha_hora`, `actor_id`, `impersonado_id`, `materia_id`, `accion`, `detalle` (JSONB), `filas_afectadas`, `ip`, `user_agent`.

`Comunicacion` (E21, C-12) contiene: `id`, `tenant_id`, `enviado_por`, `materia_id`, `estado`, `lote_id`, etc.

C-19 no agrega columnas, no agrega tablas, no genera migración. El implementador **confirma esta decisión** antes de crear ningún archivo de migración.

---

## Decisión 2 — RBAC: `auditoria:ver` con scoping, sin permisos nuevos

El permiso `auditoria:ver` ya está sembrado en C-04. No se inventa ningún permiso nuevo.

La matriz §3.3 asigna `auditoria:ver` con los siguientes scopes:

| Rol | Scope en RolPermiso | Comportamiento |
|-----|---------------------|----------------|
| ADMIN | `all` | Ve toda la actividad del tenant sin restricción |
| FINANZAS | `all` | Ve toda la actividad del tenant sin restricción |
| COORDINADOR | `own` | Ve solo la actividad de sus materias propias |

Todos los endpoints usan:
```python
Depends(require_permission("auditoria:ver", scoped=True))
```

El router recibe `(current_user, scope)` y pasa `scope` al service. El service aplica el filtro correspondiente.

### Cómo se computa "propio" del COORDINADOR

Un COORDINADOR con `scope="own"` puede ver auditoría de las materias donde tiene asignaciones activas (no soft-deleted) en el tenant:

```sql
SELECT DISTINCT materia_id
FROM asignacion
WHERE usuario_id = :actor_id
  AND tenant_id  = :tenant_id
  AND materia_id IS NOT NULL
  AND deleted_at IS NULL
```

El `AuditoriaService` ejecuta esta query al inicio de cada request con scope `"own"` y la pasa como filtro a todos los repositorios.

**Evento sin `materia_id`** (e.g., `IMPERSONACION_INICIAR`, configuración de tenant): el COORDINADOR **no los ve**. La condición es `materia_id IN (:set_materias)`, y estos eventos tienen `materia_id IS NULL`. Este es el comportamiento correcto de negocio: un COORDINADOR no tiene contexto para ver eventos globales del tenant. ADMIN/FINANZAS los ven porque tienen `scope="all"`.

**Edge case — conjunto vacío**: si un COORDINADOR no tiene ninguna asignación activa con `materia_id`, el resultado es vacío. Se devuelve 200 con listas vacías; no es un 403.

---

## Decisión 3 — Inconsistencia F9.2 "ADMIN only" vs. matriz

**Inconsistencia identificada**: F9.2 en `06_funcionalidades.md` declara `Quién: ADMIN`, pero la matriz §3.3 de `03_actores_y_roles.md` asigna `auditoria:ver` a ADMIN, FINANZAS y COORDINADOR.

**Resolución**: se sigue la **matriz** (fuente de verdad de RBAC), no la descripción funcional. La inconsistencia se documenta como un gap en la KB a corregir, pero no bloquea la implementación.

Impacto práctico: FINANZAS puede leer el log completo (F9.2), COORDINADOR puede leer el log scoped a sus materias. No se introduce ningún permiso nuevo para diferenciarlos.

> **Acción pendiente**: corregir `06_funcionalidades.md` F9.2 para reflejar `Quién: ADMIN, FINANZAS, COORDINADOR (propio)`.

---

## Decisión 4 — Estado de comunicaciones por docente: agrupación por `enviado_por`

F9.1(b) pide "estado de comunicaciones agrupado por docente". El campo `Comunicacion.destinatario` (email del alumno receptor) está **cifrado AES-256** (EncryptedString) — no es searchable ni agrupable en SQL.

**Lo que SÍ tenemos sin cifrar**: `Comunicacion.enviado_por` (UUID del docente que disparó el envío) y `Comunicacion.materia_id`.

**Interpretación correcta**: "agrupado por docente" = agrupado por el **docente remitente** (`enviado_por`), no por el alumno destinatario. Esto es también el scoping correcto para COORDINADOR (sus comunicaciones = las de los docentes con materia_id ∈ sus materias).

Query resultante:
```sql
SELECT enviado_por, estado, COUNT(*) as cantidad
FROM comunicacion
WHERE tenant_id = :tenant_id
  AND deleted_at IS NULL
  [AND materia_id IN (:materias_propias)]  -- si scope=own
GROUP BY enviado_por, estado
```

El nombre del docente se resuelve en el service con un JOIN en `user` (campos `nombre` + `apellidos` — **no cifrados**).

**No se descifra `destinatario` en masa**. No se expone email de ningún alumno en este endpoint. No existe blind-index de destinatario en la implementación actual.

---

## Decisión 5 — Métricas en vivo, sin denormalización

Todas las métricas son **agregaciones GROUP BY en vivo** sobre las tablas existentes. No se mantiene ninguna tabla de contadores, cache o snapshot.

Justificación:
- El volumen esperado de `audit_log` en un tenant es manejable con índices sobre `(tenant_id, fecha_hora)`, `(tenant_id, actor_id)` y `(tenant_id, materia_id)` — todos ya presentes desde C-05.
- La denormalización en esta etapa sería prematura optimización; si el volumen escala, se agrega un índice parcial o una vista materializada por separado.
- Los índices existentes en C-05 cubren todos los filtros previstos en F9.1 y F9.2.

---

## Decisión 6 — PII: qué mostrar, qué no

| Dato | ¿Se expone? | Razón |
|------|-------------|-------|
| `actor_id` (UUID) | ✅ | Identificador interno, no PII per se |
| `user.nombre` + `user.apellidos` | ✅ | No cifrados, necesarios para UX |
| `user.email` | ❌ | Cifrado AES-256, nunca en texto plano en ninguna respuesta |
| `user.dni`, `user.cuil`, `user.cbu` | ❌ | Cifrados, nunca expuestos |
| `Comunicacion.destinatario` | ❌ | Email cifrado, no descifrar en masa |
| `AuditLog.ip` + `user_agent` | ✅ para ADMIN/FINANZAS | Contexto de seguridad; COORDINADOR no lo necesita para su scope |
| `AuditLog.detalle` (JSONB) | ✅ para ADMIN/FINANZAS | Puede contener contexto técnico; COORDINADOR recibe `null` |

> **Regla de implementación**: los schemas de respuesta para COORDINADOR usan un subset reducido de campos (sin `ip`, `user_agent`, `detalle`). En la práctica: un schema `AuditLogPublicResponse` (sin campos de seguridad) y un `AuditLogFullResponse` (todos los campos), elegido por el service según el scope.

---

## Repositorios

### `AuditoriaRepository` (nuevo, C-19)

Separado de `AuditLogRepository` (C-05, concern de escritura). Solo lectura.

```python
class AuditoriaRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None: ...

    async def acciones_por_dia(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        materia_ids: set[UUID] | None,   # None = sin filtro (scope=all)
    ) -> list[AccionPorDiaRow]: ...
    # SELECT DATE(fecha_hora), COUNT(*) GROUP BY 1 ORDER BY 1

    async def interacciones_por_docente_materia(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        actor_id_filter: UUID | None,
        materia_ids: set[UUID] | None,
    ) -> list[InteraccionRow]: ...
    # SELECT actor_id, materia_id, accion, COUNT(*) GROUP BY 1,2,3

    async def ultimas_acciones(
        self,
        *,
        limit: int,                       # default 200, max 500
        from_date: date | None,
        to_date: date | None,
        actor_id_filter: UUID | None,
        materia_ids: set[UUID] | None,
    ) -> list[AuditLog]: ...
    # SELECT ... ORDER BY fecha_hora DESC LIMIT :limit

    async def log_completo(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        actor_id_filter: UUID | None,
        accion_filter: str | None,
        materia_ids: set[UUID] | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AuditLog], int]: ...
    # paginado, todos los filtros
```

### `ComunicacionRepository` — método adicional

```python
async def estado_por_docente(
    self,
    *,
    materia_ids: set[UUID] | None,   # None = sin filtro (scope=all)
) -> list[EstadoDocenteRow]: ...
# SELECT enviado_por, estado, COUNT(*) GROUP BY 1,2
# WHERE tenant_id=... [AND materia_id IN (...)] AND deleted_at IS NULL
```

---

## Service — `AuditoriaService`

```python
class AuditoriaService:
    def __init__(
        self,
        session: AsyncSession,
        auditoria_repo: AuditoriaRepository,
        comunicacion_repo: ComunicacionRepository,
        asignacion_repo: AsignacionRepository,   # para resolver materias propias
    ) -> None: ...

    async def _materias_propias(self, actor_id: UUID) -> set[UUID]:
        """Retorna el set de materia_id del COORDINADOR, o None si scope=all."""
        # SELECT DISTINCT materia_id FROM asignacion WHERE usuario_id=... AND deleted_at IS NULL

    async def get_panel(
        self, *, current_user: CurrentUser, scope: str | None, filtros: PanelFiltros
    ) -> PanelResponse: ...

    async def get_log(
        self, *, current_user: CurrentUser, scope: str | None, filtros: LogFiltros
    ) -> tuple[list[LogEntry], int]: ...
```

---

## Endpoints

```
GET /api/v1/auditoria/panel/acciones-por-dia          → AccionesXDiaResponse
GET /api/v1/auditoria/panel/comunicaciones-docente     → list[EstadoComunicacionXDocenteResponse]
GET /api/v1/auditoria/panel/interacciones              → list[InteraccionXDocenteMateriaResponse]
GET /api/v1/auditoria/panel/ultimas-acciones           → UltimasAccionesResponse
GET /api/v1/auditoria/log                              → PaginatedAuditLogResponse
```

Todos: `require_permission("auditoria:ver", scoped=True)`.
Todos: sin body, solo query params. Todos: 200 con lista vacía si no hay datos (nunca 404 por filtro).

---

## Decisiones abiertas (OD)

| ID | Pregunta | Impacto |
|----|----------|---------|
| OD-1 | ¿El COORDINADOR debe ver eventos sin `materia_id` (impersonación, configuración tenant)? La propuesta actual es que NO los ve. | Si la respuesta es "sí", la query de filtro cambia a `materia_id IN (:set) OR materia_id IS NULL`. |
| OD-2 | `limit` en ultimas-acciones: ¿configurable solo en el request (query param), o también hay un cap por configuración de tenant? Propuesta: query param `limit`, default=200, máx=500 hardcodeado. | Si hay cap por tenant → requiere tabla de configuración o campo en Tenant. |
| OD-3 | ¿Los campos `ip` y `user_agent` se devuelven para COORDINADOR? La propuesta dice NO (están en el schema full para ADMIN/FINANZAS, no en el público). | Si el negocio necesita que COORDINADOR los vea, cambiar el schema público. |
| OD-4 | ¿"Interacciones por docente y materia" debe incluir tipos de acción de todos los módulos, o solo los de comunicación y análisis? Propuesta: todos los códigos de `VALID_ACTION_CODES` presentes en el log, sin filtro por tipo. | Solo estético; no afecta arquitectura. |
