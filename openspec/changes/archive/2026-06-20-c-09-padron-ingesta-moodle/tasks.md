## 0. Preparación

- [x] 0.1 Agregar `MOODLE_BASE_URL: str = ""` y `MOODLE_WS_TOKEN: str = ""` en
  `backend/app/core/config.py` (Settings). Vacío = integración deshabilitada.

- [x] 0.2 Agregar campo `moodle_course_id: Mapped[str | None]` en `backend/app/models/materia.py`
  (VARCHAR(100), nullable). Este campo es necesario para la sync Moodle (OQ-C09-3).

## 1. Migración 007

- [x] 1.1 Crear `backend/alembic/versions/a1b2c3d4e5f6_007_version_padron.py`:
  - `revision = "a1b2c3d4e5f6"`, `down_revision = "c6d7e8f9a0b1"`
  - `upgrade()`:
    - ADD `moodle_course_id VARCHAR(100) NULL` a tabla `materia`
    - CREATE TABLE `version_padron` con todos los campos
    - Trigger `updated_at` para `version_padron`
    - CREATE UNIQUE INDEX `uq_version_padron_activa` (índice parcial — D-C09-1)
    - CREATE TABLE `entrada_padron` con todos los campos
    - Trigger `updated_at` para `entrada_padron`
    - CREATE INDEX `idx_entrada_padron_version`, `idx_entrada_padron_email_hash`, `idx_entrada_padron_usuario`
  - `downgrade()`: DROP TABLE `entrada_padron`, DROP TABLE `version_padron`, DROP COLUMN `materia.moodle_course_id`
- [x] 1.2 `alembic upgrade head` en `trace_test` y `trace`

## 2. Modelos SQLAlchemy

- [x] 2.1 Crear `backend/app/models/version_padron.py` — `VersionPadron(Base, BaseEntityMixin)`
- [x] 2.2 Crear `backend/app/models/entrada_padron.py` — `EntradaPadron(Base, BaseEntityMixin)` con `email_cifrado: EncryptedString`, `email_hash: String(64)`
- [x] 2.3 Actualizar `backend/app/models/__init__.py` — exportar `VersionPadron`, `EntradaPadron`
- [x] 2.4 Actualizar `backend/app/models/materia.py` — agregar campo `moodle_course_id`

## 3. Integración Moodle WS

- [x] 3.1 Crear `backend/app/integrations/__init__.py`
- [x] 3.2 Crear `backend/app/integrations/moodle_ws.py` — `MoodleParticipant`, `MoodleWSError`, `MoodleWSClientProtocol`, `MoodleWSClient` (httpx), `FakeMoodleWSClient`
- [x] 3.3 Agregar `get_moodle_client()` dependency en `backend/app/core/dependencies.py`

## 4. Parser de archivos

- [x] 4.1 Crear `backend/app/services/padron_parser.py` — detecta xlsx/csv, alias mapping, descarta filas incompletas, deduplica por email
- [x] 4.2 Agregar `openpyxl>=3.1.0` y `python-multipart>=0.0.9` en `backend/pyproject.toml`

## 5. Repositorios

- [x] 5.1 Crear `backend/app/repositories/version_padron_repository.py` — `VersionPadronRepository` con `get_active`, `deactivate_current`, `list_by_materia`
- [x] 5.2 Crear `backend/app/repositories/entrada_padron_repository.py` — `EntradaPadronRepository` con `list_by_version`, `bulk_create`
- [x] 5.3 Actualizar `backend/app/repositories/__init__.py`

## 6. Schemas Pydantic

- [x] 6.1 Crear `backend/app/schemas/padron.py` — `VersionPadronResponse`, `EntradaPadronResponse`, `PadronConEntradas`, `PadronImportResult`, `PadronPreviewEntry`, `PadronPreview`

## 7. Servicio PadronService

- [x] 7.1 Crear `backend/app/services/padron_service.py` — `import_from_file`, `import_from_moodle`, `get_padron_activo`, `vaciar`, `_resolve_usuario_id`, `_do_import`, `_build_preview`
- [x] 7.2 Actualizar `backend/app/services/__init__.py`

## 8. Router

- [x] 8.1 Crear `backend/app/api/v1/routers/padron.py` — 4 endpoints con RBAC `padron:cargar` / `padron:ver`; `MoodleWSError` → 502, ValueError → 400/403/404/503
- [x] 8.2 Registrar router en `backend/app/main.py`

## 9. Seed de permisos

- [x] 9.1 Agregar en `scripts/seed_permissions.py`: `padron:cargar`, `padron:ver`; PROFESOR scope=own, COORDINADOR scope=all, ADMIN scope=all

## 10. Tests

### `backend/tests/test_padron.py` (21 tests)

- [x] 10.1 `TestImportArchivo` (8 tests): xlsx/csv OK 201, preview sin DB write, tipo inválido 400, sin columna email 400, autolink usuario existente, autolink no cruza tenants, advertencia fila sin nombre
- [x] 10.2 `TestVersionado` (4 tests): segunda carga desactiva primera, GET version activa 200, GET sin version 404, email en response es plaintext
- [x] 10.3 `TestPIICifrado` (1 test): email cifrado en DB, plaintext en response, email_hash correcto
- [x] 10.4 `TestVaciar` (5 tests): COORDINADOR 204, PROFESOR propio 204, PROFESOR ajeno 403, sin versión 404, entradas persisten para auditoría
- [x] 10.5 `TestRBAC` (3 tests): sin padron:cargar 403, sin padron:ver 403, tenant isolation 404

### `backend/tests/test_moodle_ws.py` (8 tests)

- [x] 10.6 `TestFakeMoodleWSClient` (4 tests): retorna participantes, vacío por defecto, raises MoodleWSError, satisface Protocol
- [x] 10.7 `TestSincronizarMoodleEndpoint` (4 tests): sync OK 201, MoodleWSError → 502, sin MOODLE_BASE_URL → 503, sin moodle_course_id → 400

### Fix de infraestructura de tests

- [x] 10.8 `backend/tests/conftest.py`: autouse fixture `_clean_padron_tables` que borra `entrada_padron`/`version_padron` antes de cada test para evitar FK RESTRICT al limpiar users/tenants
- [x] 10.9 Fix en `padron_service.py`: `datetime.now(timezone.utc)` → `func.now()` en `vaciar()` (timezone mismatch con asyncpg)

## Resultado

**307 tests / 307 passed / 0 failed** — +29 tests C-09, 0 regresiones.
