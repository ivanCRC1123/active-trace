# C-17 — `programas-y-fechas-academicas` — Design

## Context

C-06 estableció Carrera, Cohorte y Materia como catálogo raíz. C-17 agrega dos entidades documentales que viven por encima de ese catálogo sin requerir Usuario ni Asignacion (C-07), lo que permite su ejecución en paralelo en Gate 5.

Fuentes: `knowledge-base/04_modelo_de_datos.md` §E15 FechaAcademica, §E16 ProgramaMateria; `knowledge-base/06_funcionalidades.md` F5.3, F5.4.

## Goals / Non-Goals

**Goals:**
- Modelos `ProgramaMateria` y `FechaAcademica` con soft-delete y tenant-scope.
- ABM completo vía REST bajo `estructura_academica:gestionar`.
- Endpoint de generación de fragmento Markdown para el LMS (F5.4).
- Extender el permiso `estructura_academica:gestionar` a COORDINADOR en el seed.
- `TipoEvaluacion` como Postgres ENUM reutilizable por C-14.
- ~25 tests TDD cubriendo CRUD, unicidad, aislamiento, fragmento y RBAC.

**Non-Goals:**
- Upload físico de archivos (almacenamiento externo): `referencia_archivo` es un campo opaco; el cliente sube el archivo a su servicio de almacenamiento y pasa la referencia resultante.
- Integración real con el LMS: el fragmento se devuelve como texto; el cliente lo publica.
- Reservas de evaluación y resultados (`ReservaEvaluacion`, `ResultadoEvaluacion`) → C-14.
- Evaluaciones formales (`Evaluacion`) → C-14.

## Decisions

### D1 — `TipoEvaluacion` como Postgres ENUM en `base.py`

```python
# backend/app/models/base.py
class TipoEvaluacion(str, enum.Enum):
    Parcial       = "Parcial"
    TP            = "TP"
    Coloquio      = "Coloquio"
    Recuperatorio = "Recuperatorio"
```

**Rationale:**
- C-14 (`Evaluacion`) usa los mismos cuatro valores; definir el type aquí con `checkfirst=True` en la migración permite que C-14 lo reutilice con `create_type=False`.
- `str` mixin → serialización directa en Pydantic y JSON (igual que `EstadoBasico`).
- Postgres ENUM → validación en el motor antes de llegar a Python; coherente con el patrón de C-06.

### D2 — Unique constraint de ProgramaMateria: (tenant_id, materia_id, carrera_id, cohorte_id)

Un programa oficial por combinación. Subir un nuevo documento para la misma combinación reemplaza el anterior (PATCH o nuevo POST devuelve 409 si ya existe sin haber eliminado el previo). El soft-delete permite recuperar la referencia anterior vía el historial de la DB.

```python
UniqueConstraint(
    "tenant_id", "materia_id", "carrera_id", "cohorte_id",
    name="uq_programa_materia_tenant_materia_carrera_cohorte",
)
```

**Alternativa descartada:** permitir múltiples versiones activas. El KB dice "centraliza los programas vigentes" (F5.3) → implica unicidad activa.

### D3 — Unique constraint de FechaAcademica: (tenant_id, materia_id, cohorte_id, tipo, numero, periodo)

Un solo registro por instancia evaluativa (ej. 1er parcial de PROG_I en cohorte MAR-2026 del período "2026-1"). El campo `numero` distingue 1er y 2do parcial.

```python
UniqueConstraint(
    "tenant_id", "materia_id", "cohorte_id", "tipo", "numero", "periodo",
    name="uq_fecha_academica_instancia",
)
```

### D4 — `referencia_archivo` es un campo opaco tipo texto

El endpoint POST/PUT de ProgramaMateria recibe `referencia_archivo` como un string (URL, key de S3, UUID, etc.) que el cliente ya obtuvo del servicio de almacenamiento externo. El backend lo almacena sin interpretarlo.

**Rationale:** No hay servicio de almacenamiento configurado en C-17. Acoplar la lógica de upload crearía dependencias de infraestructura fuera de scope. La referencia opaca es el contrato del modelo E16 del KB.

**Punto de extensión:** Si en el futuro se necesita upload directo, se agrega un endpoint multipart separado que llama al servicio de storage y luego invoca el mismo service que crea/actualiza el ProgramaMateria.

### D5 — Un único `ProgramasService` para ambas entidades

Mismo patrón que `EstructuraAcademicaService` en C-06: un servicio con métodos para las dos entidades. Ambas son operaciones de catálogo sin lógica cruzada compleja.

```
ProgramasService(session)
├── create_programa / update_programa / delete_programa / list_programas / get_programa
└── create_fecha / update_fecha / delete_fecha / list_fechas / get_fecha / generar_fragmento_lms
```

### D6 — Un archivo de router, dos prefijos

`backend/app/api/v1/routers/programas_y_fechas.py` define dos `APIRouter` separados, ambos registrados en `main.py`. Los prefijos son `/api/v1/programas` y `/api/v1/fechas-academicas`.

**Rationale:** Un archivo único mantiene la cohesión del módulo (mismo permiso, mismo servicio). Dos routers separados permiten tags distintos en la documentación OpenAPI.

### D7 — Endpoint de fragmento LMS es GET con query params

```
GET /api/v1/fechas-academicas/fragmento-lms?materia_id=…&cohorte_id=…&periodo=…
```

Devuelve `{"fragmento": "## Fechas académicas ...\n..."}` con las fechas ordenadas por tipo y número, formateado en Markdown. Permite pasar directo al portal del LMS. Si no hay fechas para los criterios dados, devuelve fragmento vacío (no 404).

### D8 — Permisos dedicados: `programas:gestionar` y `fechas_academicas:gestionar`

La matriz §3.3 del KB asigna "Gestionar estructura académica (carreras, cohortes, materias)" exclusivamente a ADMIN. Extender `estructura_academica:gestionar` a COORDINADOR le daría poder sobre el ABM de carreras/cohortes/materias — escalada de privilegios que viola el contrato.

F5.3 y F5.4 del KB establecen COORDINADOR + ADMIN para programas y fechas académicas, pero la matriz no lista estas capacidades como fila explícita. La decisión es crear dos permisos nuevos:

```python
# seed_permissions.py — PERMISOS (catálogo)
{"codigo": "programas:gestionar",           "modulo": "programas",          "descripcion": "Gestionar programas de materias"},
{"codigo": "fechas_academicas:gestionar",   "modulo": "fechas_academicas",  "descripcion": "Gestionar fechas académicas de evaluaciones"},

# PERMISSION_MATRIX["COORDINADOR"] — agregar:
"programas:gestionar":          "all",
"fechas_academicas:gestionar":  "all",

# PERMISSION_MATRIX["ADMIN"] — agregar:
"programas:gestionar":          "all",
"fechas_academicas:gestionar":  "all",
```

`estructura_academica:gestionar` queda ADMIN-only y no se modifica.

**Impacto en tests:** los fixtures de C-17 crean un COORDINADOR con `programas:gestionar` y `fechas_academicas:gestionar`; un PROFESOR recibe 403 en ambos routers.

### D9 — Validación de FKs tenant-scoped en el servicio

Al crear/actualizar ProgramaMateria o FechaAcademica, el service verifica que `materia_id`, `carrera_id` y `cohorte_id` pertenezcan al mismo `tenant_id` del actor. Si alguno es de otro tenant → 404 (no 403, para no revelar existencia). Esto se hace vía `get_by_id` del repositorio correspondiente, que ya filtra por tenant.

## Migration Plan

- Revision: `a0b1c2d3e4f5`
- Down revision: `f9a0b1c2d3e4` (010_comunicacion)
- `upgrade()`:
  1. `CREATE TYPE tipo_evaluacion` (checkfirst=True)
  2. `CREATE TABLE programa_materia`
  3. `CREATE TABLE fecha_academica`
  4. Indexes: por tenant y por (materia, cohorte) en ambas tablas
- `downgrade()`:
  1. Drop indexes
  2. `DROP TABLE fecha_academica`
  3. `DROP TABLE programa_materia`
  4. `DROP TYPE tipo_evaluacion` (checkfirst=True)

**Nota para C-14:** Al implementar `Evaluacion`, importar `TipoEvaluacion` desde `app.models.base` y usar `sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False)`.

## Risks / Trade-offs

- **`tipo_evaluacion` compartido con C-14:** Si C-14 se implementa antes que C-17 (no previsto en el plan, pero posible si el orden se invierte), C-14 debería crear el type y C-17 lo usaría con `create_type=False`. Mitigación: el `checkfirst=True` en ambas migraciones hace el orden irrelevante.
- **Referencia opaca sin validación:** El sistema no verifica que `referencia_archivo` apunte a un documento válido. Una URL rota no se detecta en el backend. Aceptable en C-17; la validación del store es responsabilidad del cliente.
- **Fragmento LMS sin template configurable:** El formato Markdown está hardcodeado en el servicio. Si diferentes tenants necesitan formatos distintos, se deberá extraer a configuración de tenant en un cambio futuro.

## Open Questions

- **Reutilización de `tipo_evaluacion` en C-14:** Se documenta en este design y en el proposal de C-14 como decisión tomada. No requiere aprobación adicional.
- **¿Se expone `cargado_at` en la respuesta de ProgramaMateria?** Sí, es útil para auditoría visual. Va en `ProgramaMateriaResponse`.
