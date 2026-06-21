# C-19 — `panel-auditoria-metricas` — Proposal

## Why

Con el log de auditoría activo desde C-05 (append-only, toda acción significativa auditada — RN-23/24) y la cola de comunicaciones funcionando desde C-12, el tenant tiene datos reales de uso pero ninguna superficie para leerlos. Los coordinadores y administradores no tienen visibilidad de qué está pasando en el sistema: quién importó calificaciones, cuántos emails se despacharon, qué docente está usando qué módulo.

C-19 habilita esa visibilidad: panel de métricas de uso (F9.1) y log completo de auditoría (F9.2), ambos **estrictamente read-only** sobre tablas ya existentes (`audit_log`, `comunicacion`).

**Governance: ALTO** — lee sobre datos de auditoría reales, expone actividad de usuarios, requiere RBAC correcto (scoping de COORDINADOR). Sin escritura, sin migración.

---

## What Changes

- **Sin migración Alembic.** No hay entidad nueva: `audit_log` (C-05) y `comunicacion` (C-12) ya existen con todos los campos necesarios.
- **Sin audit de las lecturas.** Consistente con el resto de los endpoints de lectura del sistema; los endpoints de panel y log no generan entradas en `audit_log`.
- **1 repositorio nuevo** (`AuditoriaRepository`) con las queries de agregación del panel. Separado del `AuditLogRepository` existente (concern de escritura de C-05) para preservar el principio de responsabilidad única.
- **1 método nuevo** en `ComunicacionRepository` existente: `estado_por_docente()` — agrupación por `enviado_por × estado`.
- **1 service** `AuditoriaService` que aplica el scoping de RBAC y orquesta repositorios.
- **Schemas Pydantic v2** con `extra='forbid'` para las 4 sub-vistas del panel y el log completo.
- **1 router** `/api/v1/auditoria` con 5 endpoints GET.
- **~26 tests** organizados en 2 secciones (panel + log).

---

## Capabilities

### New Capabilities

- `auditoria:ver` (ya sembrado en C-04) — **ADMIN y FINANZAS** (scope `all`): acceso completo al panel y log de toda la actividad del tenant. **COORDINADOR** (scope `own`): acceso acotado a las materias donde tiene asignaciones activas.

### Panel de Interacciones (F9.1)

- **Acciones por día** — volumen de uso del sistema en una línea de tiempo (GROUP BY fecha).
- **Estado de comunicaciones por docente** — cuántas comunicaciones tiene cada docente en cada estado (Pendiente / Enviando / Enviado / Error / Cancelado), agrupadas por `enviado_por`.
- **Interacciones por docente y materia** — conteo de acciones por tipo (código de audit) cruzado por actor y materia. Permite ver qué docente usa qué módulo.
- **Log de últimas acciones** — N registros más recientes del `audit_log` (default 200, máx configurable via query param `limit`).
- **Filtros transversales**: rango de fechas, `materia_id`, `usuario_id` (actor).

### Log Completo de Auditoría (F9.2)

- Todos los campos de `AuditLog` (id, fecha_hora, actor_id, impersonado_id, materia_id, accion, detalle JSON, filas_afectadas, ip, user_agent) con paginación.
- Filtros: rango de fechas, materia_id, actor_id, accion (código exacto).
- Disponible para ADMIN, FINANZAS y COORDINADOR (este último scoped a sus materias propias).

---

## Dependencias

- `C-05` (audit-log): tabla `audit_log` + `AuditLogRepository`.
- `C-07` (usuarios): tabla `user` para JOIN de nombre/apellidos al mostrar actor; tabla `asignacion` para computar materias propias del COORDINADOR.
- `C-12` (comunicaciones): tabla `comunicacion` + `ComunicacionRepository`.
- `C-04` (rbac): permiso `auditoria:ver` ya sembrado; `require_permission("auditoria:ver", scoped=True)`.

**No tiene dependencias hacia adelante** — se puede implementar en cualquier momento tras C-07 y C-12.
