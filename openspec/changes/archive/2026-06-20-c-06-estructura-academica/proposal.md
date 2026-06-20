# C-06 — `estructura-academica` — Proposal

## Why

Las entidades **Carrera**, **Cohorte** y **Materia** son el cimiento del dominio académico de activia-trace. Sin ellas, ningún módulo posterior puede existir: las asignaciones docentes (C-07) referencian Materia y Cohorte; el padrón (C-09) se asocia a Cohorte; las calificaciones (C-10), encuentros (C-13) y comunicaciones (C-12) cuelgan de Materia. C-06 materializa estos catálogos multi-tenant y los endpoints de administración que permiten al ADMIN de cada institución definir y mantener su estructura académica antes del inicio de cada ciclo lectivo.

El modelo propuesto sigue `04_modelo_de_datos.md` §E1–E3 y ADR-006 (Materia como catálogo único por tenant; Dictado como instancia diferida a C-07).

## What Changes

- **3 modelos ORM** (`Carrera`, `Cohorte`, `Materia`) con soft-delete, tenant-scope y enum de estado compartido (`EstadoBasico: Activa | Inactiva`).
- **1 migración Alembic 005**: 3 tablas, 4 índices, 3 unique constraints, 1 FK RESTRICT (Cohorte → Carrera), 1 PostgreSQL ENUM type.
- **3 repositorios** que extienden `BaseRepository` con tenant-scoping automático y métodos de búsqueda por campo natural.
- **1 servicio** `EstructuraAcademicaService` con validaciones de negocio: unicidad por tenant, carrera activa al crear cohorte.
- **Schemas Pydantic v2** (`Create` / `Update` / `Response` × 3 entidades), todos con `extra='forbid'`.
- **1 router** `/api/v1/admin/` con ABM completo: 5 endpoints × 3 entidades = 15 endpoints, todos guarded por `require_permission("estructura_academica:gestionar")`.
- **~30 tests** que cubren CRUD, unicidad, aislamiento multi-tenant, reglas de estado y RBAC.

## Capabilities

### New Capabilities

- `estructura:carreras` — ADMIN puede crear, consultar, actualizar y dar de baja (soft) Carreras de su tenant. Incluye cambio de estado (Activa/Inactiva).
- `estructura:cohortes` — ADMIN puede administrar Cohortes asociadas a una Carrera del tenant. La creación valida que la Carrera exista y esté activa.
- `estructura:materias` — ADMIN puede administrar el catálogo de Materias del tenant (fuente única de verdad según ADR-006). Incluye soft-delete y cambio de estado.

## Impact

| Capa | Archivos |
|------|---------|
| `backend/app/models/` | `base.py` (+ EstadoBasico enum), `carrera.py` (nuevo), `cohorte.py` (nuevo), `materia.py` (nuevo), `__init__.py` |
| `backend/app/repositories/` | `carrera_repository.py`, `cohorte_repository.py`, `materia_repository.py`, `__init__.py` |
| `backend/app/services/` | `estructura_academica_service.py`, `__init__.py` |
| `backend/app/schemas/` | `estructura_academica.py` |
| `backend/app/api/v1/routers/` | `estructura_academica.py` |
| `backend/alembic/versions/` | `[rev]_005_carrera_cohorte_materia.py` |
| `backend/app/main.py` | registro del nuevo router |
| `backend/tests/` | `test_estructura_academica.py` (~30 tests) |

**Seed**: no se requieren cambios — `estructura_academica:gestionar` ya existe en `seed_permissions.py` asignado a ADMIN con scope=all.
