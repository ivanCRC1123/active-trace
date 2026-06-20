# C-15 — `avisos-y-acknowledgment` — Proposal

## Why

Con estructura académica (C-06), usuarios (C-07) y la base de comunicaciones de C-12,
la plataforma puede agregar un canal de comunicación institucional unidireccional: el tablón
de avisos. El tablón permite a COORDINADOR/ADMIN publicar novedades segmentadas (por cohorte,
materia, rol o globales) con ventana de vigencia y acuse de recibo opcional.

El caso de uso central es **FL-09**: publicar un aviso de inicio de período a una cohorte,
controlar cuántos destinatarios lo confirmaron, y que el aviso desaparezca del tablón del
usuario una vez acusado (si `requiere_ack = True`).

## What Changes

- **2 modelos ORM**:
  - `Aviso` (E13): aviso institucional con alcance, severidad, vigencia, orden y flag de ack.
  - `AcknowledgmentAviso` (E13): registro de confirmación de lectura por usuario.
- **2 ENUMs Postgres nuevos**: `alcance_aviso` (Global/PorMateria/PorCohorte/PorRol) y
  `severidad_aviso` (Info/Advertencia/Critico).
- **1 migración Alembic 013** (`d4e5f6a7b8c9`): 2 tablas + 2 enums + índices.
- **2 repositorios**: `AvisoRepository` (CRUD + query filtrada RN-18/RN-20) y
  `AckAvisoRepository` (get-or-create idempotente).
- **1 servicio** `AvisosService` con lógica de filtrado de audiencia y confirmación.
- **Schemas Pydantic v2** para ambas entidades, todos con `extra='forbid'`.
- **1 router** `avisos.py` con endpoints de gestión (COORDINADOR/ADMIN) y de consumo
  (cualquier rol autenticado).
- **Sin cambios de permisos**: `avisos:publicar` y `comunicacion:confirmar_aviso` ya están
  sembrados desde C-04 para todos los roles correctos. No se crea ningún permiso nuevo.
- **~25 tests** cubriendo CRUD, filtrado por scope (RN-20), ventana de vigencia (RN-18),
  lógica de ack y RBAC.

## Capabilities

### Capabilities reutilizadas (sin cambio de seed)

- `avisos:publicar` — ya sembrado en COORDINADOR (all) y ADMIN (all).
  Gatea todos los endpoints de gestión: CRUD de avisos y consulta de estadísticas.
- `comunicacion:confirmar_aviso` — ya sembrado en **todos los roles** (ALUMNO, TUTOR,
  PROFESOR, COORDINADOR, NEXO, ADMIN, FINANZAS), todos con scope `all`.
  Gatea `GET /mis-avisos` y `POST /{id}/ack`.

### Permission Changes

**Ninguno.** Ambos permisos están completamente sembrados desde C-04.

## Design highlights

### Filtrado de audiencia (`mis-avisos`)

El endpoint `GET /api/v1/avisos/mis-avisos` aplica tres capas de filtro (todas en el
repositorio, vía un único query SQL):

1. **Vigencia** (RN-18): `activo = True AND inicio_en <= now AND fin_en >= now`
2. **Scope** (RN-20): el aviso es visible si su alcance coincide con el contexto del usuario:
   - `Global` → siempre visible.
   - `PorRol` → `rol_destino` coincide con alguno de los roles del usuario (vía Asignacion).
   - `PorMateria` → `materia_id` pertenece a alguna de las materias del usuario (vía Asignacion).
   - `PorCohorte` → `cohorte_id` pertenece a alguna cohorte del usuario (vía Asignacion o EntradaPadron para ALUMNO).
3. **Exclude acked** (RN-19): si `requiere_ack = True` y el usuario ya confirmó → excluir.

El servicio resuelve el contexto del usuario (roles, materias, cohortes) consultando
`AsignacionRepository` y, para ALUMNO, `EntradaPadron JOIN VersionPadron (activa=True)` —
todo dentro del mismo tenant, usando `user_id` del JWT.

### Idempotencia del ack

`POST /{id}/ack` devuelve 200 si ya existe un registro para `(aviso_id, usuario_id)`, o
crea uno nuevo y devuelve 201. Nunca falla por duplicado — idempotencia total.

### Stats sin denormalización

`GET /{id}/stats` cuenta directamente sobre `acknowledgment_aviso`:
```sql
SELECT COUNT(*) FROM acknowledgment_aviso WHERE aviso_id = :id AND deleted_at IS NULL
```
No hay contadores en `Aviso`. La KB confirma: "Los contadores se derivan consultando
`AcknowledgmentAviso`; no se almacenan como campos denormalizados."

## Impact

| Capa | Archivos |
|------|---------|
| `backend/app/models/` | `aviso.py` (nuevo, 2 clases ORM + 2 enums), `__init__.py` |
| `backend/app/repositories/` | `aviso_repository.py` (nuevo), `__init__.py` |
| `backend/app/services/` | `avisos_service.py` (nuevo), `__init__.py` |
| `backend/app/schemas/` | `avisos.py` (nuevo) |
| `backend/app/api/v1/routers/` | `avisos.py` (nuevo) |
| `backend/alembic/versions/` | `d4e5f6a7b8c9_013_aviso_acknowledgment.py` |
| `backend/app/main.py` | registro del nuevo router |
| `backend/app/core/audit_codes.py` | `AVISO_CREAR`, `AVISO_ACK` |
| `backend/tests/` | `test_avisos.py` (~25 tests) |
| `backend/tests/conftest.py` | agregar DELETE de `acknowledgment_aviso` y `aviso` al autouse fixture |
