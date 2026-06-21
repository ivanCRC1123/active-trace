# C-20 — Tasks

> Prerequisitos: C-07 ✓, C-05 ✓. Governance: BAJO (mensajería + GET perfil) / MEDIO (PATCH email).
> Resolver OQ-C20-1, OQ-C20-2, OQ-C20-3 de design.md ANTES de implementar.

---

## 0. Decisiones previas (no son código)

- [x] 0.1 Confirmar **D-C20-1**: sexo nullable VARCHAR(50) — aprobado
- [x] 0.2 Confirmar **D-C20-3**: tres tablas (HiloMensaje + HiloParticipante + MensajeInterno) — aprobado
- [x] 0.3 Confirmar **D-C20-4**: remitente_id = NULL para mensajes del sistema — aprobado

---

## 1. Migraciones

- [x] 1.1 Migración 015 (`a5b6c7d8e9f0_015_perfil_sexo.py`): ADD COLUMN sexo VARCHAR(50) nullable en tabla user
- [x] 1.2 Migración 016 (`b6c7d8e9f0a1_016_mensajeria_interna.py`): CREATE TABLE hilo_mensaje, hilo_participante, mensaje_interno
- [x] 1.3 Ejecutar alembic upgrade head en DB dev y test

---

## 2. Extender modelo User

- [x] 2.1 `backend/app/models/user.py`: campo sexo: Mapped[Optional[str]]

---

## 3. Modelos nuevos de mensajería

- [x] 3.1 Crear `backend/app/models/hilo_mensaje.py` — BaseEntityMixin
- [x] 3.2 Crear `backend/app/models/hilo_participante.py` — columnas explícitas (sin updated_at)
- [x] 3.3 Crear `backend/app/models/mensaje_interno.py` — SoftDeleteMixin + TenantScopedMixin (sin updated_at)
- [x] 3.4 Actualizar `backend/app/models/__init__.py`

---

## 4. Repositorios

- [x] 4.1 Crear `backend/app/repositories/hilo_repository.py`: list_for_user, get_by_id, is_participante, get_participantes, create_hilo, add_participante, marcar_leido
- [x] 4.2 Crear `backend/app/repositories/mensaje_repository.py`: list_for_hilo, create

---

## 5. Schemas Pydantic

- [x] 5.1 `backend/app/schemas/perfil.py`: PerfilResponse, PerfilUpdate (extra='forbid', sin cuil ni legajo)
- [x] 5.2 `backend/app/schemas/inbox.py`: HiloCreate, MensajeCreate, ParticipanteResponse, MensajeResponse, HiloResponse, HiloDetalle

---

## 6. Servicios

- [x] 6.1 `backend/app/services/perfil_service.py`: get_propio, update_propio (email dual-write + unicidad + audit PERFIL_ACTUALIZAR)
- [x] 6.2 `backend/app/services/inbox_service.py`: listar_hilos, crear_hilo, get_hilo, responder, marcar_leido — _assert_participante en toda op de hilo

---

## 7. Audit codes

- [x] 7.1 `backend/app/core/audit_codes.py`: PERFIL_ACTUALIZAR en VALID_ACTION_CODES

---

## 8. Routers

- [x] 8.1 `backend/app/api/v1/routers/perfil.py`: GET/PATCH /api/v1/perfil (self-only)
- [x] 8.2 `backend/app/api/v1/routers/inbox.py`: 5 endpoints /api/v1/inbox
- [x] 8.3 Registrar perfil.router e inbox.router en `backend/app/main.py`

---

## 9. Tests

- [x] 9.1 `backend/tests/test_perfil.py` — 20 tests (incluyendo blind-index E2E)
- [x] 9.2 `backend/tests/test_inbox.py` — 18 tests (self-scope, 403 no-participante escritura y lectura, sistema NULL, PII, tenant isolation)
- [x] 9.3 `backend/tests/conftest.py`: cleanup mensaje_interno → hilo_participante → hilo_mensaje en orden FK

---

## Resultado

**685 passed / 0 failed / 0 skipped** (667 previos + 20 perfil + 18 inbox = 685 ✓)

Logout (F11.3) reutiliza `POST /api/v1/auth/logout` de C-03 — sin código nuevo.
