# C-09 — padron-ingesta-moodle: Proposal

## Why

El catálogo académico (C-06) y los usuarios (C-07) están listos, pero no hay forma de saber
quiénes son los **alumnos** de una materia. Sin el padrón:
- No se puede cruzar calificaciones con personas (C-10).
- No se puede disparar comunicaciones dirigidas (C-12).
- No se puede determinar quién es "alumno en riesgo" (F2.2).

C-09 introduce el padrón de alumnos: el registro de quién cursa qué materia en qué cohorte,
con dos vías de carga (archivo xlsx/csv y sincronización desde Moodle Web Services) y un modelo
de versionado que preserva el historial sin perder el estado actual.

## What Changes

### Modelos nuevos

- **VersionPadron (E6)**: encabezado de una carga de padrón. Registra quién cargó el padrón,
  para qué materia × cohorte, cuándo, y si es la versión activa. Solo una versión puede estar
  `activa = True` por `(tenant_id, materia_id, cohorte_id)` a la vez; al activar una nueva
  versión, la anterior pasa a `activa = False`.

- **EntradaPadron (E6)**: una fila del padrón — un alumno en esa versión. Almacena nombre,
  apellidos, email cifrado (AES-256-GCM) + blind index HMAC-SHA256 (patrón C-07), comisión y
  regional. El campo `usuario_id` es nullable: el alumno puede aparecer en el padrón antes de
  tener cuenta en el sistema; al importar se intenta auto-vincular por `email_hash`.

### Migración

- **Migración 007**: crea `version_padron` y `entrada_padron`. Índice único parcial sobre
  `(tenant_id, materia_id, cohorte_id) WHERE activa = TRUE AND deleted_at IS NULL` en
  `version_padron` para garantizar unicidad de versión activa en la DB.

### Integración Moodle

- **`backend/app/integrations/moodle_ws.py`**: cliente abstracto (Protocol) + implementación
  concreta. Los errores del WS se capturan como `MoodleWSError` y se mapean a HTTP 502.
  El cliente concreto se inyecta vía dependency, lo que permite sustituirlo por un fake en tests.

### Parseo de archivos

- **`backend/app/services/padron_parser.py`**: parsea xlsx/csv usando `openpyxl` / `csv.reader`.
  Mapea columnas por nombre (case-insensitive). Retorna una lista de dicts con `nombre`,
  `apellidos`, `email`, `comision`, `regional`.

### Endpoints

- `POST /api/v1/padron/{materia_id}/cohortes/{cohorte_id}/importar` — carga archivo (multipart),
  parámetro `?preview=true|false`. En preview no escribe en DB. Guard: `padron:cargar`.
- `POST /api/v1/padron/{materia_id}/cohortes/{cohorte_id}/sincronizar-moodle` — sync on-demand
  desde Moodle WS. 502 si Moodle no responde. Guard: `padron:cargar`.
- `GET /api/v1/padron/{materia_id}/cohortes/{cohorte_id}` — devuelve versión activa + entradas.
  Guard: `padron:ver`.
- `DELETE /api/v1/padron/{materia_id}/cohortes/{cohorte_id}/vaciar` — vacía el padrón activo
  (scope-isolated por RN-04: PROFESOR solo vacía versiones que él mismo cargó). Guard: `padron:cargar`.

### Auditoría

Evento `PADRON_CARGAR` registrado en audit_log tras cada importación exitosa, con campos:
`version_id`, `materia_id`, `cohorte_id`, `total_entradas`, `entradas_vinculadas` (auto-linked a Usuario).

### Permisos nuevos (seed)

| Permiso | PROFESOR | COORDINADOR | ADMIN |
|---------|----------|-------------|-------|
| `padron:cargar` | scope=own | scope=all | scope=all |
| `padron:ver` | scope=own | scope=all | scope=all |

Ambos se agregan al seed de permisos (`scripts/seed_permissions.py`).

## New Capabilities

- `padron:importar-archivo` — PROFESOR y COORDINADOR pueden importar padrón desde xlsx/csv.
- `padron:preview` — Vista previa de rows parseados sin commitear a DB.
- `padron:sincronizar-moodle` — COORDINADOR/ADMIN disparan sync on-demand desde Moodle.
- `padron:versionado` — Cada carga crea una nueva VersionPadron; la anterior queda desactivada.
- `padron:auto-link` — Al importar, los emails que coincidan con Users del tenant se vinculan
  automáticamente (campo `usuario_id` en EntradaPadron).
- `padron:vaciar` — PROFESOR vacía sus propios padrones; COORDINADOR vacía cualquiera (RN-04).

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Migration | `[rev]_007_version_padron.py` | +1 |
| Models | `version_padron.py` (new), `entrada_padron.py` (new) | +2 |
| Integrations | `integrations/moodle_ws.py` (new) | +1 |
| Services | `padron_service.py` (new), `padron_parser.py` (new) | +2 |
| Repositories | `version_padron_repository.py` (new), `entrada_padron_repository.py` (new) | +2 |
| Schemas | `padron.py` (new) | +1 |
| Routers | `padron.py` (new) | +1 |
| main.py | register router | modify |
| seed | `scripts/seed_permissions.py` | modify |
| Tests | `test_padron.py` (new), `test_moodle_ws.py` (new) | +2 (~30 tests) |

## Dependencies

- **C-06** (estructura académica): tablas `materia`, `cohorte` (FK en version_padron)
- **C-07** (usuarios): tabla `user`, `EncryptedString`, `hmac_email()`, `UserRepository`
  (para auto-link email → usuario_id)
- **C-05** (audit log): `AuditService` para registrar `PADRON_CARGAR`
- C-09 **desbloquea**: C-10 (calificaciones — necesita padrón para cruzar datos)

## Governance

**MEDIO** — contiene PII de alumnos (email cifrado). Implementar con checkpoints:
surfacear al usuario el diseño del auto-link y la lógica de versionado antes de mergear.
Los campos cifrados nunca deben aparecer en logs.
