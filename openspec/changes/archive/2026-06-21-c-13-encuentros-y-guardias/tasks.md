# C-13 — Tasks

> Prerequisito: C-07 ✓, C-05 ✓, C-06 ✓.
> Governance: MEDIO. Checkpoints en scoping "propio" y generación de instancias.
> Resolver TODAS las decisiones ⚠️ de design.md ANTES de implementar.

---

## 0. Decisiones previas (bloqueantes)

- [x] 0.1 Confirmar **D-C13-1**: ¿validar fecha_inicio vs dia_semana (Opción A) o ajustar (Opción B)?
- [x] 0.2 Confirmar **D-C13-2**: ¿enum 3 estados (E10) o 4 estados con Reprogramado (RN-14)?
- [x] 0.3 Confirmar **D-C13-3**: ¿denormalizar asignacion_id en InstanciaEncuentro para scoping?
- [x] 0.4 Confirmar **D-C13-6**: ¿agregar campo `fecha DATE` a Guardia?

---

## 1. Audit codes (`backend/app/core/audit_codes.py`)

- [x] 1.1 Agregar `ENCUENTRO_CREAR`, `ENCUENTRO_EDITAR_INSTANCIA`, `GUARDIA_REGISTRAR` a `VALID_ACTION_CODES`

---

## 2. Migración 017 (`backend/alembic/versions/c7d8e9f0a1b2_017_encuentros_guardias.py`)

- [x] 2.1 Crear migración manual:
  - `revision = "c7d8e9f0a1b2"`, `down_revision = "b6c7d8e9f0a1"` (016 mensajería)
  - `upgrade()`:
    - CREATE TABLE `slot_encuentro` (ver design.md §Migración 017)
    - CREATE TABLE `instancia_encuentro`
    - CREATE TABLE `guardia`
    - Índices en `(tenant_id, materia_id)`, `(tenant_id, asignacion_id)`, `(fecha, estado)` para instancias
  - `downgrade()`: DROP en orden FK inverso
- [x] 2.2 `alembic upgrade head` en DB dev
- [x] 2.3 `alembic upgrade head` en DB test

---

## 3. Modelos (`backend/app/models/`)

- [x] 3.1 Crear `slot_encuentro.py`
- [x] 3.2 Crear `instancia_encuentro.py`
- [x] 3.3 Crear `guardia.py`
- [x] 3.4 Actualizar `backend/app/models/__init__.py` con los 3 modelos

---

## 4. Repositorios (`backend/app/repositories/`)

- [x] 4.1 Crear `slot_repository.py`
- [x] 4.2 Crear `instancia_repository.py`
- [x] 4.3 Crear `guardia_repository.py`

---

## 5. Schemas (`backend/app/schemas/`)

- [x] 5.1 Crear `encuentros.py`
- [x] 5.2 Crear `guardias.py`

---

## 6. Servicios (`backend/app/services/`)

- [x] 6.1 Crear `encuentro_service.py`
- [x] 6.2 Crear `guardia_service.py`

---

## 7. Routers (`backend/app/api/v1/routers/`)

- [x] 7.1 Crear `encuentros.py`
- [x] 7.2 Crear `guardias.py`
- [x] 7.3 Registrar ambos routers en `backend/app/main.py`

---

## 8. Tests

- [x] 8.1 Cleanup en `conftest.py` (instancia_encuentro, slot_encuentro, guardia)
- [x] 8.2 `test_encuentros.py` — 21 tests (Sección 1)
- [x] 8.3 `test_guardias.py` — 21 tests (Sección 2)

---

## 9. Fixture de test — disciplina de cleanup

- [x] Fixtures tenant-scoped; no TRUNCATE global.

---

## ✅ Completado 2026-06-21 — 730/0 verde (suite completa)
