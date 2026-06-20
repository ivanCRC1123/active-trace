# C-08 — Design Decisions

## D-C08-1: Sin migración — C-08 es puramente service/router

**Decisión**: C-08 no crea ninguna tabla nueva ni altera la tabla `asignacion`. Todas las
operaciones (masiva, clonar, vigencia-bloque, export) se expresan como INSERT/UPDATE en bulk
sobre la tabla existente.

**Justificación**: el modelo `Asignacion` (E5, C-07) ya tiene todos los campos necesarios:
`usuario_id`, `rol_id`, `materia_id`, `carrera_id`, `cohorte_id`, `comisiones`, `responsable_id`,
`desde`, `hasta`. La operación de clonar es un bulk INSERT copiando esos campos con nuevas fechas
y nuevo `cohorte_id`. La operación de vigencia-bloque es un bulk UPDATE de `desde`/`hasta`.

**Consecuencia**: el número de migración del siguiente change que necesite schema no se ve afectado.

---

## D-C08-2: `mis-equipos` usa identidad del JWT — sin permiso nuevo

**Decisión**: `GET /equipos/mis-equipos` (F4.2) usa `get_current_user` directamente, sin
`require_permission`. No se agrega ningún permiso nuevo al seed.

**Justificación**: F4.2 ("Vista de mis equipos — propia del docente") es un derecho inherente
a estar autenticado. Ver *tus propios* datos de asignación es parte de la identidad: el sistema
sabe quién sos por el JWT, y tus asignaciones son un atributo de tu perfil. El KB (§3.3) solo
define `equipos:asignar` en la matriz, sin permiso de lectura separado, lo que confirma que la
lectura propia no necesita permiso explícito.

**Regla de seguridad aplicada**: la identidad viene del JWT verificado — `current_user.user_id`.
El endpoint no acepta un `?usuario_id=` param. Ver OQ-C08 resuelto en la propuesta.

**Gestión/bloque** (F4.3–F4.7): usan `equipos:asignar` existente (COORDINADOR/ADMIN), sin cambios.

---

## D-C08-3: Router `/api/v1/equipos/` separado de `/api/v1/asignaciones/`

**Decisión**: los 6 endpoints de C-08 viven bajo `/api/v1/equipos/`. El router de C-07
(`/api/v1/asignaciones/`) sigue operando sin cambios.

**Semántica diferente**:
- `/asignaciones` → CRUD individual, orientado a administración técnica (un rol a la vez).
- `/equipos` → operaciones de dominio en bloque, orientadas al flujo del COORDINADOR.

**No se depreca `/asignaciones`**: es la interfaz de ADMIN para ajustes quirúrgicos y futuros
módulos. C-08 suma una capa de operaciones más expresivas encima.

---

## D-C08-4: Clonar (RN-12) — solo asignaciones Vigentes al momento del request

**Decisión**: la operación de clonar filtra las asignaciones del origen con:
```python
def _es_vigente(desde: date, hasta: date | None) -> bool:
    today = date.today()
    return desde <= today and (hasta is None or hasta >= today)
```
Solo las filas que devuelvan `True` se copian al destino.

**Justificación de RN-12**: "duplica todas las asignaciones vigentes". Las vencidas son historial;
copiarlas al nuevo período recrearía asignaciones que ya expiraron, lo cual confundiría el equipo.

**Campos copiados al destino**:
```
usuario_id, rol_id, carrera_id, comisiones, responsable_id
```
Campos que cambian en el destino:
```
materia_id  ← destino.materia_id   (puede ser None si el destino es solo cohorte diferente)
cohorte_id  ← destino.cohorte_id
desde       ← payload.desde
hasta       ← payload.hasta
```

**Creación en una transacción**: todas las filas nuevas se insertan en una sola transacción. Si
alguna falla (ej. FK inválida), se hace rollback completo.

---

## D-C08-5: Clonar — conflictos (ya existe asignación en destino) → omitir, no fallar

**Decisión**: si al clonar, el par `(usuario_id, rol_id, materia_id, carrera_id, cohorte_id)` ya
existe en el destino con `deleted_at IS NULL` y `estado_vigencia = Vigente`, esa fila se **omite**
(no se duplica) y se registra en `resultado.omitidos`.

**Justificación**: en el flujo FL-03 el COORDINADOR puede ejecutar el clon varias veces (por error
o para agregar los docentes que faltaban). Un error 409 en la segunda ejecución rompería el flujo.
El resultado devuelve `{ "creados": N, "omitidos": [{ "usuario_id": ..., "motivo": "ya vigente" }] }`.

**Conflictos reales** (usuario no en tenant, rol inválido) sí devuelven 422.

---

## D-C08-6: Masiva — validar-primero, luego insertar (all-or-nothing)

**Decisión**: `POST /equipos/masiva` hace dos pasadas:
1. **Validación**: verifica que todos los `usuario_ids` del request existan en el tenant y
   que `rol_id`, `materia_id`, `carrera_id`, `cohorte_id` sean válidos.
2. **Inserción**: si toda la validación pasa, inserta en una transacción.

Si algún `usuario_id` no existe → 422 con lista de IDs inválidos. No se inserta nada parcial.

**Justificación**: masiva es para el setup de cuatrimestre. Un fallo a mitad deja el equipo en
estado incompleto difícil de detectar. Mejor rechazar todo y dejar al COORDINADOR corregir el
input.

---

## D-C08-7: Vigencia bloque — identifica el equipo por contexto, no por lista de IDs

**Decisión**: el body de `PATCH /equipos/vigencia` es:
```json
{
  "materia_id": "uuid",
  "carrera_id": "uuid",
  "cohorte_id": "uuid",
  "desde": "2026-03-01",
  "hasta": "2026-07-31"
}
```
El servicio hace un `UPDATE asignacion SET desde=X, hasta=Y WHERE tenant_id=T AND materia_id=M
AND carrera_id=C AND cohorte_id=CO AND deleted_at IS NULL`.

**Justificación**: F4.6 dice "modifica las fechas de vigencia de *todas las asignaciones
pertenecientes a un equipo seleccionado*". El equipo se identifica por contexto académico, no por
una lista de IDs. Pasar IDs individuales sería un PATCH masivo del router de C-07.

**Validación**: `hasta >= desde` requerida; si no → 400. El endpoint devuelve `{"filas_afectadas": N}`.

---

## D-C08-8: Export CSV con stdlib `csv` — sin dependencias extra

**Decisión**: el endpoint de export genera CSV usando el módulo estándar `csv` de Python. No se
usa openpyxl ni pandas. La respuesta es `StreamingResponse` con:
- `Content-Type: text/csv; charset=utf-8`
- `Content-Disposition: attachment; filename="equipo.csv"`

**Columnas del CSV** (fijas):
```
apellidos, nombre, rol, materia, carrera, cohorte, comisiones, desde, hasta, estado_vigencia
```

**Joins necesarios** para los nombres legibles: el repositorio resuelve los FKs en la query
(join con `user`, `rol`, `materia`, `carrera`, `cohorte`). El servicio recibe objetos ya joinados.

**Justificación**: XLSX no agrega valor en este caso (es un simple grid). CSV es más universal
(puede abrirse en Excel, Google Sheets, etc.) y evita la dependencia de openpyxl que no existe
en el proyecto.

---

## D-C08-9: Audit `ASIGNACION_MODIFICAR` solo en operaciones de escritura

**Decisión**: las operaciones de escritura (masiva, clonar, vigencia-bloque) registran audit.
Las lecturas (mis-equipos, list, export) no generan evento de auditoría propio.

| Operación | Código audit | `filas_afectadas` |
|-----------|-------------|-------------------|
| masiva | `ASIGNACION_MODIFICAR` | N docentes creados |
| clonar | `ASIGNACION_MODIFICAR` | N asignaciones clonadas |
| vigencia-bloque | `ASIGNACION_MODIFICAR` | N filas actualizadas |

**Detalle JSON del audit para clonar**:
```json
{
  "operacion": "clonar",
  "origen": { "materia_id": "...", "carrera_id": "...", "cohorte_id": "..." },
  "destino": { "materia_id": "...", "carrera_id": "...", "cohorte_id": "..." },
  "desde": "2026-03-01",
  "hasta": "2026-07-31",
  "omitidos": 2
}
```

---

## D-C08-10: `mis-equipos` usa identidad del JWT, no parámetro de URL

**Decisión**: `GET /equipos/mis-equipos` resuelve `usuario_id` del token verificado via
`get_current_user`. No acepta un `?usuario_id=` query param. La regla de oro §3.1 KB prohíbe
que la identidad venga de la petición.

El COORDINADOR/ADMIN que quiere ver el equipo de *otro* docente usa `GET /equipos?usuario_id=X`
(que requiere `equipos:asignar`).

---

## Open Questions para C-08

| ID | Pregunta | Propuesta |
|----|----------|-----------|
| OQ-C08-1 | ¿La masiva permite crear asignaciones duplicadas (mismo user×rol×materia×cohorte vigente)? | Propuesta: rechazar con 422 la fila duplicada individual, pero mantener el all-or-nothing. |
| OQ-C08-2 | ¿El clonar también debe copiar `responsable_id`? | Sí — es parte de la jerarquía (RN-11) que también se clona. |
| OQ-C08-3 | ¿El export aplica filtros de equipo (materia × cohorte) o exporta todas las asignaciones del tenant? | Propuesta: acepta los mismos query params que `GET /equipos` — contexto optativo. |
