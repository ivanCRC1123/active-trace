# Spec: Integración, Migración y Audit Codes

> Spec transversal de C-18. Cubre la migración Alembic 014, los audit codes nuevos, el registro en main.py y la verificación del seed.

---

## Audit Codes (`backend/app/core/audit_codes.py`)

### Agregar al catálogo:

```python
# C-18 — liquidaciones-y-honorarios
GRILLA_SALARIAL_OPERAR = "GRILLA_SALARIAL_OPERAR"  # alta/edición/baja de Base, Plus y MateriaGrupo
FACTURA_ABONAR         = "FACTURA_ABONAR"           # marcar Factura como Abonada
# LIQUIDACION_CERRAR ya existe — sembrado en la sección "C-07+" del catálogo
```

### Agregar a `VALID_ACTION_CODES`:

```python
VALID_ACTION_CODES: frozenset[str] = frozenset({
    # ... existentes ...
    GRILLA_SALARIAL_OPERAR,
    FACTURA_ABONAR,
})
```

### Uso en services:

| Acción | Código | Cuándo |
|--------|--------|--------|
| Crear/editar/borrar SalarioBase, SalarioPlus, MateriaGrupo | `GRILLA_SALARIAL_OPERAR` | Toda mutación exitosa de grilla |
| Cerrar liquidaciones del período | `LIQUIDACION_CERRAR` | Al completar `cerrar_batch` |
| Marcar factura como Abonada | `FACTURA_ABONAR` | Al completar `abonar_factura` |

El campo `detalle` de cada registro de auditoría incluye como mínimo `{"tipo": ..., "operacion": ..., "id": ...}`.

---

## Migración 014 (`backend/alembic/versions/f6a7b8c9d0e1_014_liquidacion_honorarios.py`)

```python
"""014_liquidacion_honorarios

Create materia_grupo, salario_base, salario_plus, liquidacion, factura tables
and required Postgres ENUMs for C-18.

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-20
"""

revision: str = "f6a7b8c9d0e1"
down_revision: str = "d4e5f6a7b8c9"  # 013_aviso_acknowledgment
```

### `upgrade()`:

```
1. Crear Postgres ENUMs (CREATE TYPE ... IF NOT EXISTS):
   - rol_liquidable: PROFESOR, TUTOR, NEXO, COORDINADOR
   - liquidacion_estado: Abierta, Cerrada
   - factura_estado: Pendiente, Abonada

2. CREATE TABLE materia_grupo:
   - BaseEntityMixin columns (id UUID PK, tenant_id FK→tenant, created_at, updated_at, deleted_at)
   - materia_id UUID NOT NULL FK→materia(id) RESTRICT
   - grupo VARCHAR(50) NOT NULL
   - UNIQUE (tenant_id, materia_id, grupo)
   - INDEX: idx_materia_grupo_tenant (tenant_id, deleted_at)
   - INDEX: idx_materia_grupo_materia (materia_id)
   - TRIGGER trg_materia_grupo_updated_at

3. CREATE TABLE salario_base:
   - BaseEntityMixin columns
   - rol rol_liquidable NOT NULL
   - monto NUMERIC(12,2) NOT NULL
   - desde DATE NOT NULL
   - hasta DATE NULL
   - INDEX: idx_salario_base_tenant_rol (tenant_id, rol, desde)
   - TRIGGER trg_salario_base_updated_at

4. CREATE TABLE salario_plus:
   - BaseEntityMixin columns
   - grupo VARCHAR(50) NOT NULL
   - rol rol_liquidable NOT NULL
   - descripcion VARCHAR(255) NOT NULL
   - monto NUMERIC(12,2) NOT NULL
   - desde DATE NOT NULL
   - hasta DATE NULL
   - INDEX: idx_salario_plus_tenant_grupo_rol (tenant_id, grupo, rol, desde)
   - TRIGGER trg_salario_plus_updated_at

5. CREATE TABLE liquidacion:
   - BaseEntityMixin columns
   - cohorte_id UUID NOT NULL FK→cohorte(id) RESTRICT, INDEX
   - periodo VARCHAR(7) NOT NULL
   - usuario_id UUID NOT NULL FK→user(id) RESTRICT, INDEX
   - rol rol_liquidable NOT NULL
   - comisiones JSON NOT NULL DEFAULT '[]'::json
   - monto_base NUMERIC(12,2) NOT NULL
   - monto_plus NUMERIC(12,2) NOT NULL
   - total NUMERIC(12,2) NOT NULL
   - es_nexo BOOLEAN NOT NULL DEFAULT false
   - excluido_por_factura BOOLEAN NOT NULL DEFAULT false
   - datos_bancarios_incompletos BOOLEAN NOT NULL DEFAULT false
   - estado liquidacion_estado NOT NULL DEFAULT 'Abierta'
   - UNIQUE (tenant_id, cohorte_id, usuario_id, rol, periodo)
   - INDEX: idx_liquidacion_tenant_periodo (tenant_id, cohorte_id, periodo, deleted_at)
   - TRIGGER trg_liquidacion_updated_at

6. CREATE TABLE factura:
   - BaseEntityMixin columns
   - usuario_id UUID NOT NULL FK→user(id) RESTRICT, INDEX
   - periodo VARCHAR(7) NOT NULL
   - detalle TEXT NOT NULL
   - referencia_archivo TEXT NOT NULL
   - tamano_kb NUMERIC(12,3) NOT NULL
   - estado factura_estado NOT NULL DEFAULT 'Pendiente'
   - cargada_at TIMESTAMPTZ NOT NULL DEFAULT now()
   - abonada_at TIMESTAMPTZ NULL
   - INDEX: idx_factura_tenant_usuario_periodo (tenant_id, usuario_id, periodo, deleted_at)
   - INDEX: idx_factura_tenant_estado (tenant_id, estado, deleted_at)
   - TRIGGER trg_factura_updated_at
```

### `downgrade()`:

```
(triggers → tablas → tipos, en orden inverso)
1. DROP TRIGGERs
2. DROP TABLE factura
3. DROP TABLE liquidacion
4. DROP TABLE salario_plus
5. DROP TABLE salario_base
6. DROP TABLE materia_grupo
7. DROP TYPE factura_estado IF EXISTS
8. DROP TYPE liquidacion_estado IF EXISTS
9. DROP TYPE rol_liquidable IF EXISTS
```

---

## Registro en `main.py`

```python
from app.api.v1.routers import grilla_salarial, liquidaciones, facturas

app.include_router(grilla_salarial.router)
app.include_router(liquidaciones.router)
app.include_router(facturas.router)
```

---

## Verificación del seed de C-04

Verificar en `backend/scripts/seed_permissions.py` que `PERMISSION_MATRIX["FINANZAS"]` contiene los tres permisos con scope `"all"`:

```python
"FINANZAS": {
    "comunicacion:confirmar_aviso": "all",
    "auditoria:ver": "all",
    "grilla_salarial:operar": "all",          # ← presente ✓
    "liquidaciones:calcular_cerrar": "all",   # ← presente ✓
    "facturas:gestionar": "all",              # ← presente ✓
},
```

Si alguno falta, agregarlo al seed **antes** de implementar los routers. En el estado actual del repo (confirmado en `seed_permissions.py` líneas 117-123), los tres ya están.

No se modifican los `PERMISOS` del catálogo ni la matriz de otros roles.

---

## Modelos en `__init__.py`

```python
# backend/app/models/__init__.py — agregar exports:
from app.models.materia_grupo import MateriaGrupo
from app.models.salario_base import SalarioBase
from app.models.salario_plus import SalarioPlus
from app.models.liquidacion import Liquidacion
from app.models.factura import Factura
```

## Repositorios en `__init__.py`

```python
# backend/app/repositories/__init__.py — agregar exports:
from app.repositories.materia_grupo_repository import MateriaGrupoRepository
from app.repositories.salario_base_repository import SalarioBaseRepository
from app.repositories.salario_plus_repository import SalarioPlusRepository
from app.repositories.liquidacion_repository import LiquidacionRepository
from app.repositories.factura_repository import FacturaRepository
```

---

## Checklist de verificación post-implementación

- [ ] `alembic upgrade head` sin errores en `trace_test`
- [ ] `alembic downgrade -1` → `alembic upgrade head` (round-trip)
- [ ] `pytest backend/tests/test_grilla_salarial.py` — todos verdes
- [ ] `pytest backend/tests/test_liquidaciones.py` — todos verdes
- [ ] `pytest backend/tests/test_facturas.py` — todos verdes
- [ ] Suite completa sin regresiones: `pytest backend/tests/` — 0 nuevos fallos
- [ ] Cobertura: `≥90%` en reglas de negocio del módulo (cálculo, inmutabilidad, flags)
- [ ] `GRILLA_SALARIAL_OPERAR` y `FACTURA_ABONAR` en `VALID_ACTION_CODES`
- [ ] Ningún endpoint del módulo usa `Float` en tipos monetarios
- [ ] `extra='forbid'` en todos los schemas del módulo
- [ ] Ningún router del módulo accesible sin permiso FINANZAS (tests RBAC pasan)
