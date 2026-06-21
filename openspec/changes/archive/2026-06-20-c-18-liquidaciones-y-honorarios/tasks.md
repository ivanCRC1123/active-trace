# C-18 — `liquidaciones-y-honorarios` — Tasks

> Governance: CRÍTICO. No iniciar implementación sin aprobación explícita del humano.
> Orden: ejecutar en secuencia dentro de cada sección; las 3 secciones son mayormente independientes y pueden paralelizarse entre agentes una vez aprobadas.

**Estado: COMPLETO — 2026-06-20**
Suite: 618 passed, 0 failed, 0 errors.

---

## 0. Pre-requisitos y Audit Codes

- [x] 0.1 Leer design.md completo y resolver OD-3 (PA-23) con el responsable de producto antes de implementar el service de cálculo.
- [x] 0.2 Verificar seed: confirmar que `PERMISSION_MATRIX["FINANZAS"]` en `backend/scripts/seed_permissions.py` contiene `grilla_salarial:operar`, `liquidaciones:calcular_cerrar`, `facturas:gestionar`. Si alguno falta, agregarlo antes de continuar.
- [x] 0.3 Agregar a `backend/app/core/audit_codes.py`:
  - `GRILLA_SALARIAL_OPERAR = "GRILLA_SALARIAL_OPERAR"`
  - `FACTURA_ABONAR = "FACTURA_ABONAR"`
  - Ambos en `VALID_ACTION_CODES` frozenset
  - `LIQUIDACION_CERRAR` ya existe — no duplicar.

## 0b. Enums en `base.py`

- [x] 0b.1 Agregar a `backend/app/models/base.py`:
  ```python
  class RolLiquidable(str, enum.Enum):
      PROFESOR    = "PROFESOR"
      TUTOR       = "TUTOR"
      NEXO        = "NEXO"
      COORDINADOR = "COORDINADOR"

  class LiquidacionEstado(str, enum.Enum):
      Abierta = "Abierta"
      Cerrada = "Cerrada"

  class FacturaEstado(str, enum.Enum):
      Pendiente = "Pendiente"
      Abonada   = "Abonada"
  ```
- [x] 0b.2 Verificar que los tres enums están exportados desde `backend/app/models/__init__.py`.

---

## SECCIÓN 1 — Grilla Salarial

### 1. Modelos

- [x] 1.1 Crear `backend/app/models/materia_grupo.py`
- [x] 1.2 Crear `backend/app/models/salario_base.py`
- [x] 1.3 Crear `backend/app/models/salario_plus.py`
- [x] 1.4 Actualizar `backend/app/models/__init__.py` — exportar `MateriaGrupo`, `SalarioBase`, `SalarioPlus`

### 2. Repositorios

- [x] 2.1 Crear `backend/app/repositories/materia_grupo_repository.py`
- [x] 2.2 Crear `backend/app/repositories/salario_base_repository.py`
- [x] 2.3 Crear `backend/app/repositories/salario_plus_repository.py`
- [x] 2.4 Actualizar `backend/app/repositories/__init__.py`

### 3. Schemas

- [x] 3.1 Crear `backend/app/schemas/grilla_salarial.py`

### 4. Router

- [x] 4.1 Crear `backend/app/api/v1/routers/grilla_salarial.py`
- [x] 4.2 Registrar en `backend/app/main.py`

### 5. Tests de Grilla Salarial

- [x] 5.1 Crear `backend/tests/test_grilla_salarial.py` — 26 tests (TestMateriaGrupo: 8, TestSalarioBase: 10, TestSalarioPlus: 8)

---

## SECCIÓN 2 — Liquidación

### 6. Modelo

- [x] 6.1 Crear `backend/app/models/liquidacion.py`
- [x] 6.2 Actualizar `backend/app/models/__init__.py` — exportar `Liquidacion`, `LiquidacionEstado`

### 7. Repositorio

- [x] 7.1 Crear `backend/app/repositories/liquidacion_repository.py`
- [x] 7.2 Actualizar `backend/app/repositories/__init__.py`

### 8. Service LiquidacionService

- [x] 8.1 Crear `backend/app/services/liquidacion_service.py`
- [x] 8.2 Actualizar `backend/app/services/__init__.py`

### 9. Schemas

- [x] 9.1 Crear `backend/app/schemas/liquidaciones.py`

### 10. Router

- [x] 10.1 Crear `backend/app/api/v1/routers/liquidaciones.py`
- [x] 10.2 Registrar en `backend/app/main.py`

### 11. Tests de Liquidación

- [x] 11.1 Crear `backend/tests/test_liquidaciones.py` — 20 tests (TestCalculo: 8, TestCierre: 5, TestKPIs: 4, TestRBAC: 3)

---

## SECCIÓN 3 — Facturas

### 12. Modelo

- [x] 12.1 Crear `backend/app/models/factura.py`
- [x] 12.2 Actualizar `backend/app/models/__init__.py` — exportar `Factura`, `FacturaEstado`

### 13. Repositorio

- [x] 13.1 Crear `backend/app/repositories/factura_repository.py`
- [x] 13.2 Actualizar `backend/app/repositories/__init__.py`

### 14. Service FacturaService

- [x] 14.1 Crear `backend/app/services/factura_service.py`
  - Fix aplicado: `abonada_at` usa `datetime.now(timezone.utc).replace(tzinfo=None)` — columna es `TIMESTAMP WITHOUT TIME ZONE`; asyncpg rechaza datetimes timezone-aware.
- [x] 14.2 Actualizar `backend/app/services/__init__.py`

### 15. Schemas

- [x] 15.1 Crear `backend/app/schemas/facturas.py`

### 16. Router

- [x] 16.1 Crear `backend/app/api/v1/routers/facturas.py`
- [x] 16.2 Registrar en `backend/app/main.py`

### 17. Tests de Facturas

- [x] 17.1 Crear `backend/tests/test_facturas.py` — 24 tests (TestFacturaCRUD: 10, TestFacturaEstado: 4, TestFacturaFiltros: 6, TestFacturaRBAC: 4)

---

## SECCIÓN 4 — Migración

### 18. Migración Alembic 014

- [x] 18.1 Crear `backend/alembic/versions/f6a7b8c9d0e1_014_liquidacion_honorarios.py`
- [x] 18.2 Verificar `alembic upgrade head` en DB de test — sin errores
- [x] 18.3 Verificar round-trip: `alembic downgrade -1` → `alembic upgrade head`
- [x] 18.4 Suite completa: 618 passed, 0 failed, 0 errors

---

## Criterios de Aceptación

- [x] Todos los tests (70 en 3 archivos) pasan en verde
- [x] Cobertura de reglas de negocio ≥90% en el módulo
- [x] Ningún endpoint del módulo acepta request sin permiso FINANZAS (tests RBAC pasan)
- [x] Ningún monto económico usa `Float` en ninguna capa (model/schema/service)
- [x] `extra='forbid'` en todos los schemas del módulo
- [x] `LIQUIDACION_CERRAR`, `GRILLA_SALARIAL_OPERAR`, `FACTURA_ABONAR` en `VALID_ACTION_CODES`
- [x] Suite completa anterior sigue verde (0 regresiones en C-01 a C-17)
- [x] Los 3 open decisions pendientes (OD-3/PA-23, monto en Factura, base inexistente) documentados como open questions en design.md — no silenciados

---

## Follow-up (no bloqueante)

- [ ] **asyncpg NullPool exhaustion**: pool se agota a los ~20 min de suite larga → 1 `CancelledError` flaky por corrida (distinto test cada vez, pasa en aislamiento). Root cause: `NullPool` en conftest no tiene timeout configurable; considerar aumentar timeout o usar pool con tamaño mínimo antes de que los tests de frontend (C-21) aumenten la duración de la suite.
