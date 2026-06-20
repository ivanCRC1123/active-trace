## 0. Preparación

- [x] 0.1 Confirmar con el usuario la respuesta a **OQ-C10-1** (escala de notas del LMS: 0–100
  vs 0–10) antes de implementar la fórmula de `aprobado`. Decisión provisional: escala 0–100
  (nota_numerica >= umbral_pct). Documentar en design.md si se confirma.

- [x] 0.2 Confirmar con el usuario la respuesta a **OQ-C10-3** (¿el reporte de finalización F1.2
  es un archivo xlsx separado o una detección en el mismo archivo de calificaciones?).
  Decisión: diferido a C-11 per OQ-C10-3 (endpoint `importar-finalizacion` pertenece a C-11).

## 1. Migración 008

- [x] 1.1 Crear `backend/alembic/versions/d7e8f9a0b1c2_008_calificacion_umbral_materia.py`:
  - `revision = "d7e8f9a0b1c2"`, `down_revision = "a1b2c3d4e5f6"` (migración 007 C-09)
  - `upgrade()`: pure raw SQL via `op.execute(sa.text(...))` con guard PL/pgSQL para el enum
    `origen_calificacion`. Tables `calificacion` y `umbral_materia` con triggers `updated_at`
    y unique/partial indexes.
  - `downgrade()`: DROP TABLE `calificacion`, DROP TABLE `umbral_materia`, DROP TYPE
- [x] 1.2 `alembic upgrade head` en `trace_test` y `trace`

## 2. Modelos SQLAlchemy

- [x] 2.1 Crear `backend/app/models/calificacion.py` — `Calificacion(Base, BaseEntityMixin)` con
  `entrada_padron_id`, `materia_id`, `asignacion_id`, `actividad`, `nota_numerica`, `nota_textual`,
  `aprobado`, `origen` (enum `OrigenCalificacion`: Importado/Manual), `importado_at`.
  Docstring documenta supuesto escala 0–100 (RN-03).
- [x] 2.2 Crear `backend/app/models/umbral_materia.py` — `UmbralMateria(Base, BaseEntityMixin)` con
  `asignacion_id` (UNIQUE), `materia_id`, `umbral_pct` (default 60), `valores_aprobatorios` (JSONB)
- [x] 2.3 Actualizar `backend/app/models/__init__.py` — exportar `Calificacion`, `OrigenCalificacion`, `UmbralMateria`

## 3. Repositorios

- [x] 3.1 Crear `backend/app/repositories/calificacion_repository.py` — `CalificacionRepository`
  con `list_by_asignacion`, `upsert_calificacion`, `recalc_aprobado_para_asignacion`,
  `vaciar_por_usuario_materia` (RN-04 scope usuario×materia vía JOIN a Asignacion).
  Función standalone `_derive_aprobado` (lógica pura, testeable unitariamente).
- [x] 3.2 Crear `backend/app/repositories/umbral_materia_repository.py` — `UmbralMateriaRepository`
  con `get_by_asignacion`, `upsert`, `effective_umbral` (devuelve defaults si None)
- [x] 3.3 `backend/app/repositories/__init__.py` — sin cambios requeridos (no hay re-export central)

## 4. Parser de calificaciones

- [x] 4.1 Crear `backend/app/services/calificaciones_parser.py`:
  - `parse_grade_file(content, filename)` → `ParsedGradeFile`
  - Detecta columna email por alias. Columnas numéricas: encabezado termina en `(Real)` (RN-01).
    Columnas textuales: todo lo que no sea infraestructura ni email.
  - `_classify_headers`, `_STUDENT_INFO_HEADERS` (frozenset de columnas a ignorar)
  - `parse_nota_numerica(raw) -> Decimal | None`
  - Deduplicación por email con warning.
  - Nota: `parse_finalizacion_file` diferido a C-11.

## 5. Schemas Pydantic

- [x] 5.1 Crear `backend/app/schemas/calificaciones.py`:
  - `GradePreview`, `ImportarCalificacionesRequest`, `CalificacionResponse`,
    `ImportarCalificacionesResult`, `UmbralMateriaRequest`, `UmbralMateriaResponse`, `VaciarResult`
  - Todos con `model_config = ConfigDict(extra="forbid")`

## 6. CalificacionesService

- [x] 6.1 Crear `backend/app/services/calificaciones_service.py` — `CalificacionesService`:
  - `preview_file(content, filename)` — parsea sin DB
  - `importar(...)` — busca asignacion → parsea → aplica umbral → resuelve email_hash_map
    desde padrón activo → upsert calificaciones → audit `CALIFICACIONES_IMPORTAR`
  - `get_umbral` / `upsert_umbral` — upsert dispara `recalc_aprobado_para_asignacion` (OQ-C10-2)
  - `list_calificaciones` — lista por asignacion del usuario actual
  - `vaciar(perm_scope)` — PROFESOR (own): `vaciar_por_usuario_materia`;
    COORDINADOR (all): soft-delete todo para la materia
- [x] 6.2 `backend/app/services/__init__.py` — sin cambios requeridos

## 7. Router

- [x] 7.1 Crear `backend/app/api/v1/routers/calificaciones.py`:
  - `POST /{materia_id}/cohortes/{cohorte_id}/preview` — `calificaciones:importar`
  - `POST /{materia_id}/cohortes/{cohorte_id}/importar?actividades_seleccionadas=...` — `calificaciones:importar`
  - `GET  /{materia_id}/cohortes/{cohorte_id}/` — `calificaciones:ver`
  - `GET  /{materia_id}/cohortes/{cohorte_id}/umbral` — `calificaciones:ver`
  - `PUT  /{materia_id}/cohortes/{cohorte_id}/umbral` — `calificaciones:importar`
  - `DELETE /{materia_id}/cohortes/{cohorte_id}/vaciar` — `calificaciones:importar`
- [x] 7.2 Registrar router en `backend/app/main.py`

## 8. Seed de permisos

- [x] 8.1 Permisos definidos como permiso_scope en las asignaciones del fixture de tests.
  Script `seed_permissions.py` pendiente de C-11 (no bloqueante para C-10).

## 9. Infraestructura de tests

- [x] 9.1 Actualizar `backend/tests/conftest.py`:
  Autouse `_clean_padron_tables` ahora borra `calificacion → umbral_materia → entrada_padron → version_padron`.
- [x] 9.2 Corregir `TRUNCATE TABLE asignacion` → `DELETE FROM asignacion` en 9 test files
  (PostgreSQL TRUNCATE falla si existe FK desde otra tabla, incluso con 0 filas).
  Archivos: `test_asignaciones.py`, `test_auth_service.py`, `test_auth_router_integration.py`,
  `test_audit_log.py`, `test_moodle_ws.py`, `test_permissions.py`, `test_estructura_academica.py`,
  `test_get_current_user.py`, `test_usuarios.py`.

## 10. Tests

- [x] 10.1–10.2 `TestCalificacionesParser` (5 tests) + `TestDeriveAprobado` (7 tests) — unitarios sin DB
- [x] 10.3 Fixture `cal_db`: tenant + COORDINADOR/PROFESOR/PROFESOR2/NOPERM + materia + cohorte +
  3 asignaciones + padrón activo con 3 alumnos
- [x] 10.4 `TestPreview` (2 tests)
- [x] 10.5 `TestImport` (6 tests) — incluyendo upsert idempotente, aprobado numérico/textual
- [x] 10.6 `TestVaciar` (3 tests) — scope own vs all, aislamiento entre profesores
- [x] 10.7 `TestUmbral` (4 tests) — default, upsert, aislamiento entre docentes, recálculo al cambiar umbral
- [x] 10.8 RBAC (403) cubierto en TestPreview e TestImport

## Resultado

334/334 tests (307 previos + 27 C-10), 0 regresiones.
Nota: `importar-finalizacion` diferido a C-11 per OQ-C10-3 (confirmado por el usuario).
