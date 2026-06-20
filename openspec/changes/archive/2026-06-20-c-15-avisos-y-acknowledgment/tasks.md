## Estado: COMPLETADO ✓ (2026-06-20)

## 1. Modelos ORM (`backend/app/models/aviso.py`) ✓

- [x] 1.1 `AlcanceAviso`, `SeveridadAviso`, `Aviso`, `AcknowledgmentAviso` creados
- [x] 1.2 `backend/app/models/__init__.py` actualizado

## 2. Migración 013 ✓

- [x] 2.1 `d4e5f6a7b8c9_013_aviso_acknowledgment.py` creado (revision manual)
- [x] 2.2 `alembic upgrade head` ejecutado en `trace` y `trace_test`
- [x] 2.3 Round-trip verificado

## 3. Repositorios ✓

- [x] 3.1 `AvisoRepository` con `list_all`, `list_visibles_para_usuario`, `count_confirmaciones`
- [x] 3.2 `AckAvisoRepository` con `get_by_aviso_usuario`, `create_ack`
- [x] 3.3 `backend/app/repositories/__init__.py` actualizado
- [x] 3.4 `EntradaPadronRepository.list_cohortes_activas_by_usuario` añadido (fallback ALUMNO)

## 4. Schemas Pydantic ✓

- [x] 4.1–4.5 `AvisoCreate` (con model_validator scope+vigencia), `AvisoUpdate`, `AvisoResponse`, `AvisoStats`, `AckAvisoResponse`

## 5. Servicio ✓

- [x] 5.1 `AvisosService` con CRUD + `mis_avisos` + `confirmar_aviso` (idempotente)
- [x] 5.2 `backend/app/services/__init__.py` actualizado

## 6. Router ✓

- [x] 6.1–6.5 `/api/v1/avisos` con todos los endpoints; `GET /mis-avisos` registrado ANTES de `GET /{id}`; router registrado en `main.py`

## 7. Audit codes ✓

- [x] 7.1 `AVISO_CREAR` y `AVISO_ACK` en `audit_codes.py` y en `VALID_ACTION_CODES` frozenset

## 8. conftest.py ✓

- [x] 8.1 `DELETE FROM acknowledgment_aviso` y `DELETE FROM aviso` en `_clean_padron_tables`

## 9. Tests ✓ — 26/26 passing

- [x] `TestCRUDAvisos` (10 tests): CRUD todos los alcances, validaciones 422, soft-delete, tenant isolation
- [x] `TestMisAvisos` (7 tests): Global/PorRol/PorMateria/PorCohorte, vigencia, inactivo, tenant isolation, orden
- [x] `TestAcknowledgment` (6 tests): 201/200 idempotente, desaparece con requiere_ack, cross-tenant 404, stats
- [x] `TestRBAC` (3 tests): ALUMNO sin permiso, TUTOR ve mis-avisos, COORD ve stats

**Suite completa: 538/538 passing**
