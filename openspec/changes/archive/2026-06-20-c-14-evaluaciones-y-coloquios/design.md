# C-14 — `evaluaciones-y-coloquios` — Design

## Context

C-07 estableció `Usuario` y `Asignacion`. C-17 estableció `FechaAcademica` y el ENUM Postgres
`tipo_evaluacion`. C-14 agrega la capa de evaluaciones formales gestionadas: convocatoria
(Evaluacion), padrón de habilitados (ConvocadoEvaluacion), reservas (ReservaEvaluacion) y
resultados (ResultadoEvaluacion).

Fuentes: `knowledge-base/04_modelo_de_datos.md` §E14; `knowledge-base/06_funcionalidades.md`
Épica 7 (F7.1–F7.5); `knowledge-base/07_flujos_principales.md` FL-07.

## Goals / Non-Goals

**Goals:**
- 4 modelos ORM con soft-delete, tenant-scope y constraints de unicidad.
- Gestión completa de convocatorias: CRUD, importación de habilitados, métricas operativas.
- Reserva de turno con validación de cupo: una reserva resta cupo; sin cupo → 409.
- Registro y consulta de resultados por convocatoria.
- `TipoEvaluacion` reutilizado de C-17 (`create_type=False`).
- ~30 tests TDD cubriendo CRUD, cupos, RBAC y métricas.

**Non-Goals:**
- Envío de notificaciones al alumno al reservar (se delega a C-12 comunicaciones si se necesita).
- Integración directa con padrón de C-09 (`EntradaPadron`): la importación de habilitados es
  independiente (F7.2 importa su propio padrón de coloquio, no replica `VersionPadron`).
- Gestión de fechas calendario de evaluaciones (`FechaAcademica`) — pertenece a C-17.

## Decisions

### D1 — `TipoEvaluacion` reutilizado de C-17

```python
# En Evaluacion.tipo:
sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False)
```

El ENUM Postgres ya existe desde la migración 011. C-14 lo referencia con `create_type=False`.
`TipoEvaluacion` se importa desde `app.models.base` sin redefinirlo.

### D2 — `cupo_total` en Evaluacion (extensión del KB)

El KB define `dias_disponibles: entero — ventana de inscripción en días` pero no modela el cupo
explícitamente. Sin embargo, CHANGES.md §C-14 tests exige "reserva resta cupo, sin cupo rechaza"
y F7.4 muestra "cupos libres" como métrica.

Decisión: agregar `cupo_total: int` a `Evaluacion`.

```
cupos_libres = cupo_total - count(ReservaEvaluacion WHERE evaluacion_id = X AND estado = 'Activa')
```

El cupo es **total** (no por día), para mantener el modelo simple y alineado con el KB que no
define subturnos. Si el negocio necesita cupos por día en el futuro, se agrega una tabla de
turnos sin romper el contrato actual.

### D3 — `ConvocadoEvaluacion` como extensión del KB (patrón EntradaPadron)

El KB E14 no modela explícitamente el padrón de habilitados, pero F7.2 ("importar alumnos a una
convocatoria") y la métrica F7.1 "total de alumnos cargados" implican una tabla de convocados.

```
ConvocadoEvaluacion {
  id            : UUID
  tenant_id     : UUID
  evaluacion_id : UUID → evaluacion.id RESTRICT
  usuario_id    : UUID | None → user.id RESTRICT  (null si no tiene cuenta aún)
  nombre        : str    — plaintext (igual que EntradaPadron §E6)
  apellidos     : str    — plaintext
  email_cifrado : str    — EncryptedString TypeDecorator (AES-256-GCM)
  email_hash    : str    — HMAC-SHA256 blind index para deduplicación sin exponer plaintext
}
```

Mismo patrón PII que `EntradaPadron` (C-09): `email_cifrado` + `email_hash`. El servicio llama
`hmac_email(email)` de `app.core.encryption` para generar el hash antes de insertar.

`convocados` (métrica F7.1) = `COUNT(convocado_evaluacion WHERE evaluacion_id = X AND deleted_at IS NULL)`.

Unicidad por `(tenant_id, evaluacion_id, usuario_id)` cuando `usuario_id IS NOT NULL` (DB).
Para alumnos sin cuenta (`usuario_id IS NULL`), la deduplicación en el servicio usa `email_hash`.

### D4 — Ciclo de vida de ReservaEvaluacion

```
Activa → Cancelada
```

Solo dos estados. Una reserva no se elimina físicamente (soft-delete); se marca `Cancelada`.
Al cancelar, el cupo liberado queda disponible para otra reserva inmediatamente.

Constraint: un alumno solo puede tener **una reserva Activa** por evaluacion_id:

```python
UniqueConstraint(
    "tenant_id", "evaluacion_id", "alumno_id",
    name="uq_reserva_evaluacion_activa",
)
```

Nota: la unicidad solo impide duplicados al nivel de BD pero permite que el mismo alumno reserve
en distintas convocatorias. La lógica de "solo puede tener una activa" se refuerza en el
service (filtra por estado='Activa' antes de insertar).

### D5 — Permiso `coloquios:gestionar` para coordinación

La matriz §3.3 del KB no tiene fila explícita para coloquios. F7.2/F7.3/F7.4 dicen
COORDINADOR/ADMIN; F7.5 dice ADMIN. La elección de un único `coloquios:gestionar` con scope
`all` para ambos roles cubre todos los endpoints de gestión, incluyendo el cierre/registro de
resultados que FL-07 atribuye al COORDINADOR.

`evaluacion:reservar` (ya sembrado) cubre el endpoint de reserva/cancelación del ALUMNO.

### D6 — Un servicio `ColoquiosService` para todas las entidades

Mismo patrón que `ProgramasService` en C-17: un servicio único, un archivo de repositorio.

```
ColoquiosService(session)
├── create_convocatoria / update_convocatoria / delete_convocatoria
├── list_convocatorias / get_convocatoria
├── importar_convocados(evaluacion_id, filas: list[dict]) → int
├── metricas_panel() → MetricasPanel
├── metricas_convocatoria(evaluacion_id) → MetricasConvocatoria
├── reservar_turno(evaluacion_id, alumno_id, fecha_hora) → ReservaEvaluacion
├── cancelar_reserva(reserva_id, alumno_id) → ReservaEvaluacion
├── list_reservas(evaluacion_id) → list[ReservaEvaluacion]
├── registrar_resultado(evaluacion_id, alumno_id, nota_final) → ResultadoEvaluacion
└── list_resultados(evaluacion_id) → list[ResultadoEvaluacion]
```

### D7 — Router único con endpoints diferenciados por permiso

```
/api/v1/coloquios                           ← coloquios:gestionar (COORDINADOR/ADMIN)
  GET   /                   listado con métricas (F7.4)
  POST  /                   crear convocatoria (F7.3)
  GET   /metricas-panel     panel global (F7.1)
  GET   /{id}               detalle con métricas (F7.4 / F7.5)
  PATCH /{id}               editar convocatoria
  DELETE /{id}              soft delete
  POST  /{id}/convocados    importar lote de alumnos (F7.2)
  GET   /{id}/reservas      agenda de reservas activas (F7.5)
  POST  /{id}/resultados    registrar resultado (F7.5)
  GET   /{id}/resultados    registro académico (F7.5)

/api/v1/coloquios/{id}/mis-reservas         ← evaluacion:reservar (ALUMNO)
  POST  /                   reservar turno
  DELETE /{reserva_id}      cancelar reserva propia
```

Los endpoints de alumno están en el mismo router pero con `Depends` diferente.

### D8 — Validación de FK tenant-scoped en el servicio

Al crear/actualizar `Evaluacion`, el servicio verifica que `materia_id` y `cohorte_id`
pertenezcan al mismo `tenant_id` del actor (igual que en C-17 para `ProgramaMateria`).
Si alguno es de otro tenant → 404 (no 403, para no revelar existencia).

### D9 — Soft-delete en las 4 tablas; `ResultadoEvaluacion` se actualiza con auditoría

`ResultadoEvaluacion` admite UPDATE directo: si ya existe un resultado para `(evaluacion_id,
alumno_id)`, el servicio actualiza `nota_final` y registra la acción `RESULTADO_REGISTRAR` en el
AuditLog con `detalle={"nota_anterior": old, "nota_nueva": new}`. Esto permite corregir notas
preservando trazabilidad sin duplicar filas.

Las otras 3 tablas (`Evaluacion`, `ConvocadoEvaluacion`, `ReservaEvaluacion`) solo tienen
soft-delete, nunca hard delete.

## Migration Plan

- Revision: `b1c2d3e4f5a6`
- Down revision: `a0b1c2d3e4f5` (011 — programa_materia + fecha_academica, de C-17)
- `upgrade()`:
  1. `op.create_table("evaluacion", ...)` — BaseEntityMixin + materia_id, cohorte_id, tipo
     (Enum TipoEvaluacion create_type=False), instancia, dias_disponibles, cupo_total
  2. `op.create_table("convocado_evaluacion", ...)` — BaseEntityMixin + evaluacion_id,
     usuario_id (nullable), nombre, apellidos, email (cifrado)
  3. `op.create_table("reserva_evaluacion", ...)` — BaseEntityMixin + evaluacion_id, alumno_id,
     fecha_hora, estado (Enum: Activa/Cancelada, checkfirst=True)
  4. `op.create_table("resultado_evaluacion", ...)` — BaseEntityMixin + evaluacion_id, alumno_id,
     nota_final
  5. Índices: `idx_evaluacion_tenant`, `idx_evaluacion_materia_cohorte`,
     `idx_convocado_evaluacion_id`, `idx_reserva_evaluacion_id`, `idx_resultado_evaluacion_id`
- `downgrade()`:
  1. Drop índices
  2. Drop tablas en orden inverso (resultado → reserva → convocado → evaluacion)
  3. `sa.Enum(name='estado_reserva').drop(op.get_bind(), checkfirst=True)`

**Nota**: `tipo_evaluacion` ya existe desde migración 011. NO se crea ni se elimina en 012.

## Risks / Trade-offs

- **Cupo total, no por día**: simplifica el modelo pero no soporta "3 cupos el martes y 5 el
  jueves". Si el negocio lo necesita se agrega una tabla `TurnoEvaluacion` sin impactar reservas
  existentes (el FK pasa de `evaluacion_id` a `turno_id`).
- **ConvocadoEvaluacion independiente del padrón de C-09**: la importación de habilitados
  repite lógica similar a `EntradaPadron`. Si el negocio quiere derivar los habilitados
  automáticamente del padrón activo, se agrega un endpoint de "poblar desde padrón" en C-14
  sin cambiar el modelo.
- **Reserva sin notificación al alumno**: el módulo de comunicaciones (C-12) puede emitir
  confirmación por email, pero C-14 no llama a C-12 directamente para mantener bajo el
  acoplamiento. Un futuro evento/hook puede conectarlos.
- **Una reserva activa por alumno × evaluacion**: el único constraint en BD es por columnas
  `(tenant_id, evaluacion_id, alumno_id)`; la lógica "solo activa" se verifica en el service.
  Si falla la transacción entre la comprobación y el insert, podría crearse una segunda reserva
  activa. Mitigación: usar `SELECT FOR UPDATE` en el service antes de insertar.

## Open Questions resueltas

- **`cupo_total = 0` = sin límite** — CONFIRMADO (D9 / schema `cupo_total: int, ge=0`).
- **Resultados: UPDATE directo + audit log** — CONFIRMADO: se actualiza `nota_final` en el
  registro existente y se registra `RESULTADO_REGISTRAR` con `old → new` en el detalle JSON.
