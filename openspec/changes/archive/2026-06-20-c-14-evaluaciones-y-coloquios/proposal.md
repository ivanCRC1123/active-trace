# C-14 — `evaluaciones-y-coloquios` — Proposal

## Why

Con usuarios y asignaciones disponibles desde C-07, la plataforma puede implementar el ciclo
completo de las evaluaciones formales: convocar alumnos, gestionar cupos, registrar reservas y
consolidar resultados. Este módulo cubre la Épica 7 del KB (F7.1–F7.5) y el flujo FL-07
(coloquio: convocatoria a evaluación).

El caso de uso central es el **coloquio final**: coordinación crea una convocatoria con cupos
por día, importa el padrón de habilitados, y los alumnos reservan su turno. El módulo también
sirve para parciales y recuperatorios que requieran turnos gestionados.

## What Changes

- **4 modelos ORM**:
  - `Evaluacion` (E14): convocatoria de evaluación con materia, cohorte, tipo y cupos totales.
  - `ConvocadoEvaluacion`: extensión de E14 — padrón de alumnos habilitados para la convocatoria (necesario para F7.2 e indicador "convocados" de F7.1).
  - `ReservaEvaluacion` (E14): reserva de turno por alumno con estado Activa/Cancelada.
  - `ResultadoEvaluacion` (E14): nota final por alumno en la evaluación.
- **1 migración Alembic 012** (`b1c2d3e4f5a6`): 4 tablas, sin ENUM nuevo (reutiliza `tipo_evaluacion` de C-17 con `create_type=False`), índices y constraints.
- **1 repositorio** (`EvaluacionRepository`) con métodos de cupo y métricas.
- **1 servicio** (`ColoquiosService`) que encapsula toda la lógica: creación de convocatoria, importación de convocados, validación de cupo, reserva, cancelación y resultados.
- **Schemas Pydantic v2** para las 4 entidades + DTOs de métricas, todos con `extra='forbid'`.
- **1 router** `coloquios.py` con dos conjuntos de endpoints bajo permisos distintos: gestión (COORDINADOR/ADMIN) y reserva de turno (ALUMNO).
- **Actualización del seed**: un permiso nuevo (`coloquios:gestionar`) para COORDINADOR + ADMIN. `evaluacion:reservar` ya está sembrado (ALUMNO + ADMIN).
- **~30 tests** cubriendo CRUD de convocatorias, importación de convocados, reserva con cupo, cancelación, métricas y RBAC.

## Capabilities

### New Capabilities

- `coloquios:gestionar` — COORDINADOR y ADMIN pueden crear convocatorias (F7.3), importar el
  padrón de habilitados (F7.2), consultar el listado con métricas operativas (F7.4), el panel
  de métricas globales (F7.1) y registrar/consultar resultados (F7.5).
- `evaluacion:reservar` — ya sembrado desde C-04. ALUMNO puede reservar y cancelar su turno
  en una convocatoria con cupo disponible (FL-07 paso 4).

### Permission Changes

Se crea un permiso nuevo en el catálogo:

- `coloquios:gestionar` — COORDINADOR (all) + ADMIN (all). Gatea todos los endpoints de
  gestión de `/api/v1/coloquios`.
  - Base: F7.2 ("Quién: COORDINADOR, ADMIN"), F7.3 ("Quién: COORDINADOR, ADMIN"), F7.4
    ("Quién: COORDINADOR, ADMIN"), F7.5 ("Quién: ADMIN" — cubierto por scope all en ADMIN).

`evaluacion:reservar` no se modifica (ya está sembrado, ALUMNO all + ADMIN all).

### Inconsistencia FL-07 vs F7.x (documentada, sin bloquear)

FL-07 atribuye la preparación de la convocatoria al PROFESOR ("Preparación (PROFESOR)"), pero
F7.2 y F7.3 dicen explícitamente COORDINADOR/ADMIN. Se opta por **F7.x como fuente canónica
de permisos**, dado que:

1. La matriz de capacidades (§3.3) no menciona coloquios bajo el rol PROFESOR.
2. F7.5 (Admin global) confirma que la gestión es exclusiva de coordinación/admin.
3. COORDINADOR ya puede importar padrón (`padron:cargar`) y gestionar estructura.

Si en el futuro el negocio habilita al PROFESOR para crear convocatorias, se agrega
`coloquios:gestionar` con scope `own` al seed de PROFESOR, sin cambio de modelo.

## Impact

| Capa | Archivos |
|------|---------|
| `backend/app/models/` | `evaluacion.py` (nuevo, 4 clases ORM), `__init__.py` |
| `backend/app/repositories/` | `evaluacion_repository.py` (nuevo), `__init__.py` |
| `backend/app/services/` | `coloquios_service.py` (nuevo), `__init__.py` |
| `backend/app/schemas/` | `coloquios.py` (nuevo) |
| `backend/app/api/v1/routers/` | `coloquios.py` (nuevo) |
| `backend/alembic/versions/` | `b1c2d3e4f5a6_012_evaluacion_reserva_resultado.py` |
| `backend/app/main.py` | registro del nuevo router |
| `backend/scripts/seed_permissions.py` | `coloquios:gestionar` para COORDINADOR + ADMIN |
| `backend/tests/` | `test_coloquios.py` (~30 tests) |
