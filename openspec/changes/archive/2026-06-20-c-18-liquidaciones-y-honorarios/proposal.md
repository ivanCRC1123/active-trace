# C-18 — `liquidaciones-y-honorarios` — Proposal

## Why

Con la estructura académica (C-06), los usuarios, asignaciones y datos bancarios cifrados (C-07) ya disponibles, el módulo de FINANZAS puede operar el flujo económico del tenant: configurar la grilla salarial, liquidar honorarios docentes por período y gestionar los comprobantes de facturantes independientes.

Este change implementa las tres piezas del flujo:

1. **Grilla salarial** — ABM de SalarioBase (por rol) y SalarioPlus (por grupo de materias × rol), con vigencia temporal versionada. Incluye la tabla de mapeo `materia_grupo` que resuelve el gap PA-22 (materia → categoría de plus).
2. **Liquidación mensual** — cálculo automático de `Base + Σ(Plus × N_comisiones)` por docente × cohorte × período; cierre inmutable (RN-22/37). Segmentación contable: general / NEXO / facturantes (RN-36/38).
3. **Facturas** — gestión de comprobantes de docentes con `facturador=True`; flujo paralelo al de liquidación (RN-35/39/40).

**Governance: CRÍTICO** — montos económicos reales, inmutabilidad por cierre, identidad siempre desde sesión. Se propone el diseño completo aquí; la implementación requiere aprobación explícita antes de escribir código.

---

## What Changes

- **5 modelos ORM** (`MateriaGrupo`, `SalarioBase`, `SalarioPlus`, `Liquidacion`, `Factura`) con soft-delete y tenant-scope.
- **1 tabla de mapeo `materia_grupo`** que resuelve PA-22: vincula `materia_id` a una clave de grupo de plus configurable por tenant.
- **1 migración Alembic 014** (`f6a7b8c9d0e1`): 5 tablas, 3 Postgres ENUMs nuevos (`rol_liquidable`, `liquidacion_estado`, `factura_estado`), índices y constraint de unicidad de vigencia.
- **5 repositorios** que extienden `BaseRepository`.
- **2 servicios**: `LiquidacionService` (cálculo, cierre, KPIs, historial) y `FacturaService` (CRUD, abonar).
- **Schemas Pydantic v2** con `extra='forbid'` para las 3 secciones.
- **3 routers**: `/api/v1/grilla-salarial`, `/api/v1/liquidaciones`, `/api/v1/facturas`.
- **2 nuevos audit codes** en `audit_codes.py`: `GRILLA_SALARIAL_OPERAR`, `FACTURA_ABONAR`. (`LIQUIDACION_CERRAR` ya existe.)
- **Sin cambios en el seed** — los 3 permisos FINANZAS (`grilla_salarial:operar`, `liquidaciones:calcular_cerrar`, `facturas:gestionar`) ya están sembrados desde C-04.
- **~40 tests TDD** organizados en 3 archivos de test.

---

## Capabilities

### New Capabilities

- `grilla_salarial:operar` (FINANZAS-only) — Crear, editar y consultar entradas de SalarioBase y SalarioPlus con vigencia temporal. Gestionar el mapeo `materia_grupo` (qué materias pertenecen a qué grupo de plus). Genera audit `GRILLA_SALARIAL_OPERAR`.

- `liquidaciones:calcular_cerrar` (FINANZAS-only) — Disparar el cálculo de liquidaciones para una dupla (cohorte, período AAAA-MM): genera o recalcula registros `Liquidacion` por cada docente activo. Cerrar liquidaciones (inmutabiliza). Consultar historial de períodos cerrados. Obtener KPIs: total_sin_factura y total_con_factura. Genera audit `LIQUIDACION_CERRAR`.

- `facturas:gestionar` (FINANZAS-only) — CRUD de `Factura` para docentes con `facturador=True`. Marcar facturas como abonadas (Pendiente → Abonada). Filtrar por docente, período y estado. Genera audit `FACTURA_ABONAR`.

### Permission Changes

Ninguna — los tres permisos ya están en `PERMISSION_MATRIX["FINANZAS"]` del seed C-04. ADMIN **no** tiene estos permisos (confirmado en `seed_permissions.py` líneas 86-123).

---

## Impact

| Capa | Archivos nuevos / modificados |
|------|-------------------------------|
| `backend/app/models/` | `materia_grupo.py` ✦, `salario_base.py` ✦, `salario_plus.py` ✦, `liquidacion.py` ✦, `factura.py` ✦, `base.py` (+3 enums), `__init__.py` |
| `backend/app/repositories/` | `materia_grupo_repository.py` ✦, `salario_base_repository.py` ✦, `salario_plus_repository.py` ✦, `liquidacion_repository.py` ✦, `factura_repository.py` ✦, `__init__.py` |
| `backend/app/services/` | `liquidacion_service.py` ✦, `factura_service.py` ✦, `__init__.py` |
| `backend/app/schemas/` | `grilla_salarial.py` ✦, `liquidaciones.py` ✦, `facturas.py` ✦ |
| `backend/app/api/v1/routers/` | `grilla_salarial.py` ✦, `liquidaciones.py` ✦, `facturas.py` ✦ |
| `backend/alembic/versions/` | `f6a7b8c9d0e1_014_liquidacion_honorarios.py` ✦ |
| `backend/app/main.py` | registro de los 3 nuevos routers |
| `backend/app/core/audit_codes.py` | `+GRILLA_SALARIAL_OPERAR`, `+FACTURA_ABONAR` |
| `backend/tests/` | `test_grilla_salarial.py` ✦, `test_liquidaciones.py` ✦, `test_facturas.py` ✦ |

✦ = archivo nuevo

---

## Scope: ¿Un solo C-18 o fases?

**Decisión: un único C-18 cohesivo.**

Fundamento: las tres secciones están acopladas semánticamente (la liquidación consume la grilla y marca `excluido_por_factura`; las facturas son el lado opuesto del flag `facturador`), comparten los mismos guards FINANZAS, y el frontend C-24 los consume juntos. Partir el change en C-18a/C-18b añadiría dependencias nuevas en el árbol sin reducir el riesgo real. El tamaño (~40 tests, 5 modelos) es mayor que C-17 pero manejable en una sesión.

Si en la implementación la grilla salarial + mapeo materia_grupo resultan más complejos de lo previsto (ej. por resolución de PA-22), se puede extraer como C-18a sin reescribir el árbol de dependencias ya que la grilla no tiene estado compartido con el resto.
