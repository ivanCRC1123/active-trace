## C-11 — analisis-atrasados-reportes: Tasks

> Orden secuencial. Cada task depende de las anteriores.
> Marcar `[x]` al completar antes de pasar a la siguiente.

---

## 0. Decisiones cerradas (no requieren confirmación)

- [x] **OQ-C11-1 CERRADO**: vocabulario "completado" → parámetro de sistema en `settings.FINALIZACION_VALORES_COMPLETADO`, default = `["completado","completed","sí","si","yes","true","1","finalizado","finished","done"]`.
- [x] **OQ-C11-2 CERRADO**: "nota final" = `pct_actividades_aprobadas` (aprobadas/total×100). Campo etiquetado explícitamente, no como "nota".
- [x] **OQ-C11-3 CERRADO**: paginación aceptada (limit=100 default, max 500).
- [x] **OQ-C11-4 CERRADO**: faltante = sin calificacion Y NO (textual + finalizado). Ver D-C11-3.
- [x] **PERMISOS**: ningún permiso nuevo. Reutilizar `atrasados:ver`, `entregas:detectar_sin_corregir`, `calificaciones:importar` del seed C-04.

---

## 1. Migración 009

- [x] **1.1** Crear `backend/alembic/versions/e8f9a0b1c2d3_009_finalizacion_actividad.py`:
  - `revision = "e8f9a0b1c2d3"`, `down_revision = "d7e8f9a0b1c2"` (migración 008 C-10)
  - `upgrade()`: tabla `finalizacion_actividad` con índices (ver design.md §Migración 009)
  - `downgrade()`: `DROP TABLE finalizacion_actividad`

- [x] **1.2** `alembic upgrade head` en `trace_test` y `trace`.

---

## 2. Modelo SQLAlchemy

- [x] **2.1** Crear `backend/app/models/finalizacion_actividad.py`:
  `FinalizacionActividad(Base, BaseEntityMixin)` con `entrada_padron_id`, `materia_id`,
  `asignacion_id`, `actividad` (VARCHAR 500), `finalizado` (BOOL NOT NULL DEFAULT FALSE).

- [x] **2.2** Actualizar `backend/app/models/__init__.py` → exportar `FinalizacionActividad`.

---

## 3. Parser de finalización

- [x] **3.1** Crear `backend/app/services/finalizacion_parser.py`:
  - `parse_finalizacion_file(content, filename) -> ParsedFinalizacionFile`
  - Reutiliza `_STUDENT_INFO_HEADERS` de `calificaciones_parser.py`
  - `_COMPLETED_VALUES` frozenset con vocabulario default (D-C11-10)
  - `_is_completed(raw: str) -> bool`
  - Soporta xlsx y csv (mismo patrón que calificaciones_parser)
  - Deduplicación por email con warning
  - `ValueError` si no hay columna de email

---

## 4. Repositorios

- [x] **4.1** Crear `backend/app/repositories/finalizacion_repository.py`:
  `FinalizacionRepository(BaseRepository[FinalizacionActividad])` con:
  - `vaciar_por_asignacion_materia(asignacion_id, materia_id) -> int`
  - `bulk_insert(rows: list[dict]) -> int`
  - `list_sin_corregir(materia_id, asignacion_id) -> list[SinCorregirRow]` (ver spec sin-corregir)
  - `count_por_asignacion(asignacion_id, materia_id) -> int` (para detectar si hay datos)

- [x] **4.2** Crear `backend/app/repositories/analisis_repository.py`:
  `AnalisisRepository` (no hereda de BaseRepository — solo tiene métodos de query):
  - `atrasados(tenant_id, materia_id, cohorte_id, asignacion_id?) -> list[AtrasadoRow]`
  - `ranking(tenant_id, materia_id, cohorte_id, asignacion_id?) -> list[RankingRow]`
  - `notas_finales(tenant_id, materia_id, cohorte_id, asignacion_id?) -> list[NotaFinalRow]`
  - `reporte_rapido(tenant_id, materia_id, cohorte_id, asignacion_id?) -> ReporteRapidoRow`
  - `monitor(tenant_id, filters: MonitorFilters) -> tuple[list[MonitorRow], int]`

  Todas las queries usan `AsyncSession` directamente. SQL vía `sa.text(...)` o ORM
  (preferir ORM para queries simples, `sa.text` para las CTEs complejas).

---

## 5. Schemas Pydantic

- [x] **5.1** Crear `backend/app/schemas/analisis.py`:
  - `FinalizacionImportResult`
  - `AlumnoAtrasado`, `AtrasadosResponse`
  - `RankingItem`, `RankingResponse`
  - `ReporteRapidoResponse`
  - `NotaFinalAlumno`, `NotasFinalesResponse`
  - `EntregaSinCorregir`, `SinCorregirResponse`
  - `MonitorItem`, `MonitorResponse`, `MonitorFilters`

  Todos con `model_config = ConfigDict(extra="forbid")`.

---

## 6. AnalisisService

- [x] **6.1** Crear `backend/app/services/analisis_service.py`:
  - `importar_finalizacion(materia_id, cohorte_id, current_user, content, filename) -> FinalizacionImportResult`
  - `get_atrasados(materia_id, cohorte_id, current_user, scope) -> AtrasadosResponse`
  - `get_ranking(materia_id, cohorte_id, current_user, scope) -> RankingResponse`
  - `get_reporte_rapido(materia_id, cohorte_id, current_user, scope) -> ReporteRapidoResponse`
  - `get_notas_finales(materia_id, cohorte_id, current_user, scope) -> NotasFinalesResponse`
  - `exportar_notas_finales(materia_id, cohorte_id, current_user, scope) -> str`  (CSV string)
  - `get_sin_corregir(materia_id, cohorte_id, current_user, scope) -> SinCorregirResponse`
  - `exportar_sin_corregir(materia_id, cohorte_id, current_user, scope) -> str`  (CSV string)
  - `get_monitor(current_user, scope, filters: MonitorFilters) -> MonitorResponse`

  El servicio resuelve `asignacion_id` del usuario actual y pasa `None` si scope=all.
  Audit `CALIFICACIONES_IMPORTAR` tras import de finalización.

---

## 7. Router

- [x] **7.1** Crear `backend/app/api/v1/routers/analisis.py` con los 9 endpoints
  (ver spec analisis-router).

- [x] **7.2** Registrar en `backend/app/main.py`:
  `from app.api.v1.routers.analisis import router as analisis_router`
  `app.include_router(analisis_router)`

---

## 8. Permisos — sin cambios en seed

- [x] **8.1** Los permisos `atrasados:ver` y `entregas:detectar_sin_corregir` ya están en el seed (C-04). No se modifica `seed_permissions.py`.

---

## 9. Infraestructura de tests

- [x] **9.1** Actualizar `backend/tests/conftest.py`:
  Añadir `finalizacion_actividad` al autouse de limpieza, en el orden FK-safe:
  `calificacion → finalizacion_actividad → umbral_materia → entrada_padron → version_padron`.

---

## 10. Tests del parser (unitarios, sin DB)

- [x] **10.1** Crear `backend/tests/test_finalizacion_parser.py`:
  - 6 tests cubriendo: xlsx, csv, case-insensitive, sin email, duplicado, todas las actividades.
  (Ver spec finalizacion-actividad §Tests requeridos)

---

## 11. Tests de integración (con DB)

- [x] **11.1** Crear `backend/tests/test_analisis.py` con fixture `analisis_db`:
  - Mismo patrón que `cal_db` de C-10: tenant + roles (COORDINADOR, PROFESOR, TUTOR, NOPERM)
    + materia + cohorte + asignaciones + padrón activo con 4 alumnos + calificaciones semilla.
  - Los 4 alumnos: uno al día (todas aprobadas), uno bajo umbral, uno faltante, uno con texto sin corregir.

- [x] **11.2** Tests de import de finalización (6 tests): ver spec finalizacion-actividad.

- [x] **11.3** Tests de atrasados (8 tests): ver spec atrasados-y-ranking.

- [x] **11.4** Tests de ranking (3 tests): ver spec atrasados-y-ranking.

- [x] **11.5** Tests de reporte rápido (2 tests): ver spec atrasados-y-ranking.

- [x] **11.6** Tests de notas finales (6 tests): ver spec notas-finales.

- [x] **11.7** Tests de sin corregir (7 tests): ver spec sin-corregir.

- [x] **11.8** Tests de monitor (9 tests): ver spec monitores.

---

## Resultado esperado

- Total tests: ~334 previos (C-10) + ~47 C-11 ≈ **381 tests**.
- 0 regresiones.
- `≥80% cobertura` líneas; `≥90% reglas de negocio` (RN-06, RN-07, RN-08, RN-09 cubiertas).
