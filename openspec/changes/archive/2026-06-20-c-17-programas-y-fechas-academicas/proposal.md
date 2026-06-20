# C-17 — `programas-y-fechas-academicas` — Proposal

## Why

Con la estructura académica (Carrera, Cohorte, Materia) ya disponible desde C-06, la coordinación necesita dos herramientas complementarias para el setup de cada cuatrimestre:

1. **Programas de materia** — centraliza el documento oficial (sílabo) por materia × carrera × cohorte, accesible a todos los actores autorizados y publicable en el LMS.
2. **Fechas académicas** — calendariza las instancias evaluativas (parciales, TPs, coloquios) por materia × cohorte, con vista tabular y generación de fragmento listo para el aula virtual.

Ambas son funcionalidades de Governance BAJO, puramente documentales y de referencia: no tienen ciclos de vida complejos ni reglas de negocio críticas. Se implementan en un único change que comparte permiso, servicio y migración.

La dependencia es solo C-06 (Carrera, Cohorte, Materia existen); no requiere C-07 (sin referencias a Usuario/Asignacion), lo que permite ejecutarlo en paralelo con C-07 en el plan de 3 agentes (Gate 5).

## What Changes

- **2 modelos ORM** (`ProgramaMateria` E16, `FechaAcademica` E15) con soft-delete, tenant-scope y `TipoEvaluacion` enum compartido.
- **1 migración Alembic 011**: 2 tablas, 1 nuevo ENUM Postgres `tipo_evaluacion`, 4 índices, 2 unique constraints.
- **2 repositorios** (`ProgramaMateriaRepository`, `FechaAcademicaRepository`) que extienden `BaseRepository`.
- **1 servicio** `ProgramasService` con validaciones de negocio: FKs tenant-scoped, unicidad, lógica de generación de fragmento LMS.
- **Schemas Pydantic v2** (`Create` / `Update` / `Response` × 2 entidades), todos con `extra='forbid'`.
- **1 archivo de router** (`programas_y_fechas.py`) con dos prefijos: `/api/v1/programas` y `/api/v1/fechas-academicas`, ambos bajo `estructura_academica:gestionar`.
- **Actualización de seed**: dos permisos nuevos (`programas:gestionar`, `fechas_academicas:gestionar`) sembrados para ADMIN + COORDINADOR. `estructura_academica:gestionar` no se toca (sigue ADMIN-only).
- **~25 tests** cubriendo CRUD, unicidad, aislamiento tenant, fragmento LMS, RBAC COORDINADOR/ADMIN.

## Capabilities

### New Capabilities

- `programas:gestionar` — ADMIN y COORDINADOR pueden subir/asociar el programa oficial de una materia para una combinación específica de carrera × cohorte. La referencia al documento es opaca (el upload físico se realiza externamente al servicio de almacenamiento).
- `fechas-academicas:gestionar` — ADMIN y COORDINADOR pueden registrar y editar fechas de parciales, TPs y coloquios por materia × cohorte × período. Vista tabular y calendario disponibles.
- `fechas-academicas:fragmento-lms` — Endpoint de generación de contenido: dada una materia + cohorte (+ período opcional), devuelve un fragmento Markdown listo para publicar en el aula virtual del LMS.

### Permission Changes

Se crean dos permisos nuevos en el catálogo; `estructura_academica:gestionar` queda intacto (ADMIN-only, solo gatea carreras/cohortes/materias de C-06).

- `programas:gestionar` — ADMIN + COORDINADOR. Gatea `/api/v1/programas`.
  - Base: F5.3 ("Quién: ADMIN, COORDINADOR") del KB.
- `fechas_academicas:gestionar` — ADMIN + COORDINADOR. Gatea `/api/v1/fechas-academicas`.
  - Base: F5.4 ("Quién: COORDINADOR, ADMIN") del KB.

Ambos se agregan en `PERMISOS` y en `PERMISSION_MATRIX["ADMIN"]` + `PERMISSION_MATRIX["COORDINADOR"]` de `seed_permissions.py`.

## Impact

| Capa | Archivos |
|------|---------|
| `backend/app/models/` | `base.py` (+ `TipoEvaluacion` enum), `programa_materia.py` (nuevo), `fecha_academica.py` (nuevo), `__init__.py` |
| `backend/app/repositories/` | `programa_materia_repository.py`, `fecha_academica_repository.py`, `__init__.py` |
| `backend/app/services/` | `programas_service.py` (nuevo), `__init__.py` |
| `backend/app/schemas/` | `programas_y_fechas.py` (nuevo) |
| `backend/app/api/v1/routers/` | `programas_y_fechas.py` (nuevo) |
| `backend/alembic/versions/` | `a0b1c2d3e4f5_011_programa_materia_fecha_academica.py` |
| `backend/app/main.py` | registro del nuevo router |
| `backend/scripts/seed_permissions.py` | COORDINADOR gana `estructura_academica:gestionar` |
| `backend/tests/` | `test_programas_y_fechas.py` (~25 tests) |
