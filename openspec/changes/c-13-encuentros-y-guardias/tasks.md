# C-13 — Tasks

> Prerequisito: C-07 ✓, C-05 ✓, C-06 ✓.
> Governance: MEDIO. Checkpoints en scoping "propio" y generación de instancias.
> Resolver TODAS las decisiones ⚠️ de design.md ANTES de implementar.

---

## 0. Decisiones previas (bloqueantes)

- [ ] 0.1 Confirmar **D-C13-1**: ¿validar fecha_inicio vs dia_semana (Opción A) o ajustar (Opción B)?
- [ ] 0.2 Confirmar **D-C13-2**: ¿enum 3 estados (E10) o 4 estados con Reprogramado (RN-14)?
- [ ] 0.3 Confirmar **D-C13-3**: ¿denormalizar asignacion_id en InstanciaEncuentro para scoping?
- [ ] 0.4 Confirmar **D-C13-6**: ¿agregar campo `fecha DATE` a Guardia?

---

## 1. Audit codes (`backend/app/core/audit_codes.py`)

- [ ] 1.1 Agregar `ENCUENTRO_CREAR`, `ENCUENTRO_EDITAR_INSTANCIA`, `GUARDIA_REGISTRAR` a `VALID_ACTION_CODES`

---

## 2. Migración 017 (`backend/alembic/versions/c7d8e9f0a1b2_017_encuentros_guardias.py`)

- [ ] 2.1 Crear migración manual:
  - `revision = "c7d8e9f0a1b2"`, `down_revision = "b6c7d8e9f0a1"` (016 mensajería)
  - `upgrade()`:
    - CREATE TABLE `slot_encuentro` (ver design.md §Migración 017)
    - CREATE TABLE `instancia_encuentro`
    - CREATE TABLE `guardia`
    - Índices en `(tenant_id, materia_id)`, `(tenant_id, asignacion_id)`, `(fecha, estado)` para instancias
  - `downgrade()`: DROP en orden FK inverso
- [ ] 2.2 `alembic upgrade head` en DB dev
- [ ] 2.3 `alembic upgrade head` en DB test

---

## 3. Modelos (`backend/app/models/`)

- [ ] 3.1 Crear `slot_encuentro.py`:
  - `class SlotEncuentro(Base, BaseEntityMixin)`
  - Campos según design.md: titulo, hora (Time), dia_semana (String), fecha_inicio (Date nullable), cant_semanas (Integer), fecha_unica (Date nullable), meet_url, vig_desde, vig_hasta
- [ ] 3.2 Crear `instancia_encuentro.py`:
  - `class InstanciaEncuentro(Base, BaseEntityMixin)`
  - slot_id nullable FK→slot_encuentro, asignacion_id FK→asignacion, materia_id FK→materia
  - fecha (Date), hora (Time), titulo, estado (String), meet_url, video_url, comentario
- [ ] 3.3 Crear `guardia.py`:
  - `class Guardia(Base, BaseEntityMixin)`
  - asignacion_id, materia_id, carrera_id, cohorte_id, dia (String), fecha (Date nullable), horario (String), estado (String), comentarios
- [ ] 3.4 Actualizar `backend/app/models/__init__.py` con los 3 modelos

---

## 4. Repositorios (`backend/app/repositories/`)

- [ ] 4.1 Crear `slot_repository.py`:
  - `SlotRepository`
  - `list_by_tenant(materia_id=None) → list[SlotEncuentro]`
  - `list_by_asignaciones(asignacion_ids, materia_id=None) → list[SlotEncuentro]`
  - `get_by_id(slot_id) → SlotEncuentro | None` (tenant-scoped)
  - `create(data) → SlotEncuentro`
  - `soft_delete(slot_id) → bool`

- [ ] 4.2 Crear `instancia_repository.py`:
  - `InstanciaRepository`
  - `list_by_tenant(filtros) → list[InstanciaEncuentro]` (estado, fecha_desde, fecha_hasta, materia_id, slot_id)
  - `list_by_asignaciones(asignacion_ids, filtros) → list[InstanciaEncuentro]`
  - `get_by_id(instancia_id) → InstanciaEncuentro | None`
  - `create_bulk(instancias: list[InstanciaEncuentro]) → list[InstanciaEncuentro]`
  - `update(instancia_id, data: dict) → InstanciaEncuentro | None`
  - `cancel_by_slot(slot_id) → int` — cancela instancias Programado de un slot

- [ ] 4.3 Crear `guardia_repository.py`:
  - `GuardiaRepository`
  - `list_by_tenant(filtros) → list[Guardia]`
  - `list_by_asignaciones(asignacion_ids, filtros) → list[Guardia]`
  - `get_by_id(guardia_id) → Guardia | None`
  - `create(data) → Guardia`
  - `update(guardia_id, data: dict) → Guardia | None`

---

## 5. Schemas (`backend/app/schemas/`)

- [ ] 5.1 Crear `encuentros.py`:
  - `SlotCreate`, `SlotResponse`, `SlotConInstanciasResponse`
  - `InstanciaUpdate`, `InstanciaResponse`
  - Todos con `extra='forbid'`
- [ ] 5.2 Crear `guardias.py`:
  - `GuardiaCreate`, `GuardiaUpdate`, `GuardiaResponse`
  - Con `extra='forbid'`

---

## 6. Servicios (`backend/app/services/`)

- [ ] 6.1 Crear `encuentro_service.py`:
  - `EncuentroService`:
    - `_validar_modo_slot(data: SlotCreate)` — raises ValueError si invariante roto
    - `_validar_fecha_dia_semana(fecha, dia_semana)` — raises ValueError si no coinciden (D-C13-1 opción A)
    - `_generar_instancias(slot) → list[InstanciaEncuentro]` — algoritmo de fechas
    - `crear_slot(current_user, data) → SlotConInstanciasResponse` — crea slot + instancias + audit ENCUENTRO_CREAR
    - `listar_slots(current_user, materia_id=None) → list[SlotResponse]` — scoping propio/todo
    - `get_slot(current_user, slot_id) → SlotConInstanciasResponse` — 404/403 si no autorizado
    - `eliminar_slot(current_user, slot_id)` — soft-delete + cancela instancias Programado
    - `listar_instancias(current_user, filtros) → list[InstanciaResponse]`
    - `editar_instancia(current_user, instancia_id, data) → InstanciaResponse` — 403 si no propietario (own)
    - `fragmento_lms(current_user, materia_id, slot_id=None) → str` — Markdown formateado

- [ ] 6.2 Crear `guardia_service.py`:
  - `GuardiaService`:
    - `_assert_propietario_o_admin(current_user, guardia)` — PermissionError si no autorizado
    - `registrar(current_user, data) → GuardiaResponse` — estado forzado a Pendiente + audit GUARDIA_REGISTRAR
    - `listar(current_user, filtros) → list[GuardiaResponse]`
    - `editar(current_user, guardia_id, data) → GuardiaResponse` — 403 si no propietario
    - `exportar_csv(current_user, filtros) → str` — requiere scope=all

---

## 7. Routers (`backend/app/api/v1/routers/`)

- [ ] 7.1 Crear `encuentros.py`:
  - `router = APIRouter(prefix="/api/v1/encuentros", tags=["encuentros"])`
  - `POST /slots` (201) — require_permission("encuentros:gestionar")
  - `GET /slots` (200) — require_permission("encuentros:gestionar")
  - `GET /slots/{slot_id}` (200) — require_permission("encuentros:gestionar")
  - `DELETE /slots/{slot_id}` (204) — require_permission("encuentros:gestionar")
  - `GET /instancias` (200) — require_permission("encuentros:gestionar")
  - `PATCH /instancias/{instancia_id}` (200) — require_permission("encuentros:gestionar")
  - `GET /fragmento-lms` (200) — require_permission("encuentros:gestionar")

- [ ] 7.2 Crear `guardias.py`:
  - `router = APIRouter(prefix="/api/v1/guardias", tags=["guardias"])`
  - `POST /` (201) — require_permission("guardias:registrar")
  - `GET /` (200) — require_permission("guardias:registrar")
  - `PATCH /{guardia_id}` (200) — require_permission("guardias:registrar")
  - `GET /export` (200 CSV) — require_permission("guardias:registrar") + scope=all check en service

- [ ] 7.3 Registrar ambos routers en `backend/app/main.py`

---

## 8. Tests

### `backend/tests/conftest.py`
- [ ] 8.1 Agregar cleanup en `_clean_padron_tables` (orden FK):
  ```python
  await db_session.execute(text("DELETE FROM instancia_encuentro"))
  await db_session.execute(text("DELETE FROM slot_encuentro"))
  await db_session.execute(text("DELETE FROM guardia"))
  ```
  Antes de: `DELETE FROM asignacion` / `DELETE FROM materia` (que ya están en la cadena).

### `backend/tests/test_encuentros.py`
- [ ] 8.2 Clases:
  - `TestSlotCrearRecurrente` (~5 tests) — incluyendo validación fecha/dia_semana
  - `TestSlotCrearUnico` (~3 tests)
  - `TestListarInstancias` (~3 tests) — scoping propio vs global
  - `TestEditarInstancia` (~5 tests) — propio 200, ajeno PROFESOR 403, ajeno TUTOR 200
  - `TestFragmentoLMS` (~3 tests) — Programado, Realizado, sin Cancelado
  - `TestTenantIsolation` (~2 tests)

### `backend/tests/test_guardias.py`
- [ ] 8.3 Clases:
  - `TestGuardiaRegistrar` (~5 tests) — propio 201, ajeno 403, estado inicial Pendiente
  - `TestGuardiaListar` (~3 tests) — scoping own vs all
  - `TestGuardiaEditar` (~3 tests)
  - `TestGuardiaExport` (~2 tests) — COORDINADOR 200, TUTOR 403
  - `TestTenantIsolation` (~1 test)

---

## 9. Fixture de test — disciplina de cleanup

Las 3 tablas nuevas se borran ANTES que `asignacion`, `materia`, `carrera`, `cohorte` en `_clean_padron_tables`:

```
DELETE FROM instancia_encuentro   ← referencia slot_encuentro
DELETE FROM slot_encuentro         ← referencia asignacion, materia
DELETE FROM guardia                ← referencia asignacion, materia, carrera, cohorte
(... resto del cleanup existente ...)
```

Fixture de test scoped por tenant: NO usar TRUNCATE global. Borrar solo las filas del tenant del test.

---

## Resumen de archivos

| Archivo | Acción |
|---|---|
| `backend/app/core/audit_codes.py` | MODIFY — 3 nuevos códigos |
| `backend/alembic/versions/c7d8e9f0a1b2_017_encuentros_guardias.py` | NUEVO |
| `backend/app/models/slot_encuentro.py` | NUEVO |
| `backend/app/models/instancia_encuentro.py` | NUEVO |
| `backend/app/models/guardia.py` | NUEVO |
| `backend/app/models/__init__.py` | MODIFY |
| `backend/app/repositories/slot_repository.py` | NUEVO |
| `backend/app/repositories/instancia_repository.py` | NUEVO |
| `backend/app/repositories/guardia_repository.py` | NUEVO |
| `backend/app/schemas/encuentros.py` | NUEVO |
| `backend/app/schemas/guardias.py` | NUEVO |
| `backend/app/services/encuentro_service.py` | NUEVO |
| `backend/app/services/guardia_service.py` | NUEVO |
| `backend/app/api/v1/routers/encuentros.py` | NUEVO |
| `backend/app/api/v1/routers/guardias.py` | NUEVO |
| `backend/app/main.py` | MODIFY — registrar 2 routers |
| `backend/tests/conftest.py` | MODIFY — cleanup 3 tablas |
| `backend/tests/test_encuentros.py` | NUEVO (~21 tests) |
| `backend/tests/test_guardias.py` | NUEVO (~14 tests) |
