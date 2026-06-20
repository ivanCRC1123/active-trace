## C-12 — comunicaciones-cola-worker: Tasks

> Orden secuencial. Cada task depende de las anteriores.
> Todas completadas — change archivado 2026-06-20.

---

## 1. Migración 010

- [x] **1.1** `backend/alembic/versions/f9a0b1c2d3e4_010_comunicacion.py`
  - `revision = "f9a0b1c2d3e4"`, `down_revision = "e8f9a0b1c2d3"` (migración 009 C-11)
  - `ALTER TABLE tenant ADD COLUMN requiere_aprobacion_comunicacion BOOLEAN NOT NULL DEFAULT TRUE`
  - `CREATE TABLE comunicacion (...)` con TIMESTAMPTZ, FSM CHECK, trigger updated_at, 4 índices

- [x] **1.2** `alembic upgrade head` en `trace_test` y `trace`.

---

## 2. Modelo y tipos

- [x] **2.1** `backend/app/models/comunicacion.py`:
  - `EstadoComunicacion` (enum), `TRANSICIONES_VALIDAS`, `validar_transicion()`
  - `Comunicacion(Base, BaseEntityMixin)` con `EncryptedString(destinatario)`, `DateTime(timezone=True)` en `aprobado_at`/`enviado_at`

- [x] **2.2** `backend/app/models/tenant.py` — agregar `requiere_aprobacion_comunicacion: Mapped[bool]`

- [x] **2.3** `backend/app/models/__init__.py` — exportar `Comunicacion`, `EstadoComunicacion`

- [x] **2.4** `backend/app/core/audit_codes.py` — agregar `COMUNICACION_APROBAR` al catálogo cerrado `VALID_ACTION_CODES`

- [x] **2.5** `backend/app/core/config.py` — sección Email dispatcher + sección Worker

---

## 3. Email dispatcher

- [x] **3.1** `backend/app/integrations/email_dispatcher.py`:
  - `EmailDispatchError`, `AbstractEmailDispatcher` (Protocol)
  - `FakeSender` (sent=[{subject,body}] — sin PII), `SmtpSender` (aiosmtplib)
  - `build_dispatcher_from_settings()` — factory por `EMAIL_BACKEND`

---

## 4. Repository

- [x] **4.1** `backend/app/repositories/comunicacion_repository.py`:
  - Scoped: `bulk_create`, `set_estado` (valida FSM), `aprobar_lote`, `cancelar_lote`
  - Lectura: `get_by_id`, `list_by_lote`, `list_by_usuario`, `list_tenant`, `resumen_estados`
  - Cross-tenant (worker): `list_enviando_all_tenants`, `set_estado_worker`

---

## 5. Service

- [x] **5.1** `backend/app/services/comunicacion_service.py`:
  - `preview()` — sin DB writes (RN-16)
  - `crear_lote()` — N Comunicacion + audit COMUNICACION_ENVIAR
  - `aprobar_lote()` — audit COMUNICACION_APROBAR
  - `cancelar_lote()`, `cancelar_individual()`, `get_lote()`, `list_comunicaciones()`
  - `_necesita_aprobacion()` — RN-17 simplificada (scope + masividad), documentada

---

## 6. Schemas

- [x] **6.1** `backend/app/schemas/comunicaciones.py`:
  - Requests: `PreviewRequest`, `CrearLoteRequest` (`extra='forbid'`)
  - Responses: `PreviewItem`, `PreviewResponse`, `LoteCreado`, `ComunicacionItem` (sin `destinatario`), `ResumenEstados`, `LoteDetalle`, `AprobacionResponse`, `CancelacionLoteResponse`, `CancelacionIndividualResponse`, `ComunicacionListResponse`

---

## 7. Router + main

- [x] **7.1** `backend/app/api/v1/routers/comunicaciones.py` — 7 endpoints
- [x] **7.2** `backend/app/main.py` — `app.include_router(comunicaciones.router)`

---

## 8. Worker

- [x] **8.1** `backend/app/workers/main.py`:
  - `dispatch_loop(dispatcher, session_factory, poll_interval)` — asyncio polling cross-tenant
  - `main()` — entrypoint con factory de dispatcher y session
  - Invariante PII: nunca loguea `com.destinatario`

---

## 9. Tests

- [x] **9.1** `backend/tests/conftest.py` — agregar `DELETE FROM comunicacion` a `_clean_padron_tables`
- [x] **9.2** `backend/tests/test_comunicaciones.py` — 29 tests (FSM, preview, lote, aprobación, cancelación, worker, audit, PII, multitenancy, scope)

---

## Resultado

- 29 tests nuevos: 29/29 PASSED
- Suite completa: 412/412 PASSED, 0 failures
- Camino crítico C-01→C-12 completo
