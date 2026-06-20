# C-11 — Design Decisions

## D-C11-1: FinalizacionActividad se persiste en DB (vs. in-memory cross)

**Decisión**: el reporte de finalización se importa y persiste como tabla `finalizacion_actividad`
(un row por alumno×actividad×asignacion), igual que `Calificacion` persiste las notas.

**Alternativa descartada**: calcular "sin corregir" en memoria: parsear el archivo de finalización
al vuelo, cruzarlo con calificaciones en el servicio y retornar el resultado sin tocar la DB.

**Por qué se descarta**:
- El usuario no debería re-subir el archivo en cada consulta de "sin corregir".
- El cruce en memoria bloquea la posibilidad de filtrar/paginar desde la DB.
- Sin persistencia, el monitor (F2.7/F2.8) no puede consultar el estado de finalización.
- La persistencia sigue el patrón de `Calificacion`: un archivo → un conjunto de rows en DB.

---

## D-C11-2: Import de finalizacion es destructivo por asignacion (mismo patrón que calificaciones)

**Decisión**: al importar el reporte de finalización para una `(materia_id, cohorte_id)` y
`asignacion_id` activa, el servicio hace soft-delete de las `FinalizacionActividad` previas de
esa misma asignacion antes de insertar las nuevas.

**Justificación**: el padrón puede actualizarse entre cargas; el docente quiere ver el estado
actual, no el acumulado. El mismo patrón destructivo per asignacion de `Calificacion` aplica
aquí (RN-04: el scope es siempre `usuario_id × materia_id`).

**Scope**:
- PROFESOR (scope=own): limpia y carga solo las filas de su `asignacion_id`.
- COORDINADOR/ADMIN (scope=all): limpia todas las `FinalizacionActividad` para el
  `(tenant_id, materia_id, cohorte_id)` antes de insertar.

---

## D-C11-3: "Faltante" = sin calificacion Y NO (actividad textual con finalización registrada)

**Decisión**: se considera "faltante" a un alumno que aparece en el padrón activo
(`entrada_padron` de la `version_padron` activa) pero no tiene ninguna fila en `calificacion`
para alguna de las actividades que SÍ tienen calificaciones para otros alumnos (en la
misma `materia_id`, `asignacion_id`).

**Formalización**:
```sql
-- Actividades en scope (al menos un alumno las tiene)
activities AS (
    SELECT DISTINCT actividad FROM calificacion
    WHERE tenant_id = :t AND materia_id = :m AND asignacion_id = :a AND deleted_at IS NULL
),
-- Alumnos del padrón activo
padron AS (
    SELECT ep.id, ep.nombre, ep.apellidos, ep.email_cifrado, ep.email_hash
    FROM entrada_padron ep
    JOIN version_padron vp ON ep.version_id = vp.id
    WHERE vp.tenant_id = :t AND vp.materia_id = :m AND vp.cohorte_id = :c
      AND vp.activa = TRUE AND vp.deleted_at IS NULL AND ep.deleted_at IS NULL
),
-- Faltantes: alumnos que no tienen calificacion para alguna actividad
faltantes AS (
    SELECT p.id, p.nombre, p.apellidos, a.actividad
    FROM padron p CROSS JOIN activities a
    WHERE NOT EXISTS (
        SELECT 1 FROM calificacion c
        WHERE c.entrada_padron_id = p.id AND c.actividad = a.actividad
          AND c.asignacion_id = :a AND c.deleted_at IS NULL
    )
)
```

**Refinamiento clave (OQ-C11-4)**: si un alumno no tiene calificacion para una actividad textual
PERO tiene `finalizado=True` en `finalizacion_actividad` para esa actividad, esa situación es
**"sin corregir" (RN-07)**, NO "faltante". El docente entregó el trabajo; está esperando la nota.
Mezclarlo con "faltante" confundiría al docente: el alumno SÍ entregó.

**Fórmula revisada**:
```
faltante(alumno, actividad) =
    NOT EXISTS calificacion(alumno, actividad)
    AND NOT (
        actividad ∈ actividades_textuales
        AND EXISTS finalizacion_actividad(alumno, actividad, finalizado=True)
    )
```

**Justificación**: usar el set de actividades importadas como referencia evita falsos positivos.
La exclusión de "sin corregir" preserva la semántica de RN-06 ("sin entregar") sin mezclarla
con RN-07 ("entregado pero sin nota").

---

## D-C11-4: "Atrasado" = union de faltantes + aprobado=False (sin deduplicar razones)

**Decisión**: la respuesta de atrasados incluye, por alumno, dos listas:
- `actividades_faltantes: list[str]` — actividades sin calificacion.
- `actividades_bajo_umbral: list[str]` — calificaciones con `aprobado=False`.

Un alumno aparece en la lista si tiene al menos un ítem en cualquiera de las dos listas.
Las dos listas son mutuamente excluyentes por construcción: si un alumno tiene calificacion
para una actividad (aunque sea bajo umbral), esa actividad no aparece en `actividades_faltantes`.

**Valor**: el docente puede ver DE UNA VEZ qué alumnos están atrasados y POR QUÉ, sin dos
queries separados. Insumo directo para C-12 (comunicaciones).

---

## D-C11-5: Ranking ordenado por count(aprobado=True) DESC, con posición absoluta

**Decisión**: el ranking retorna la lista de alumnos con ≥1 actividad aprobada (RN-09)
ordenada descendente por `total_aprobadas`. El campo `posicion` es la posición 1-indexed
en ese orden.

```
[
  { "nombre": "García Ana", "total_aprobadas": 8, "total_actividades": 10, "posicion": 1 },
  { "nombre": "López Juan", "total_aprobadas": 7, "total_actividades": 10, "posicion": 2 },
  ...
]
```

Alumnos con 0 aprobadas: excluidos (RN-09), no aparecen ni con posicion=0.

---

## D-C11-6: "Notas finales" = % de actividades aprobadas — campo etiquetado como tal

**Decisión** (confirmada — OQ-C11-2 cerrado):
```
pct_actividades_aprobadas = count(aprobado=TRUE) / count(DISTINCT actividad) × 100
```

Calculado por alumno sobre las calificaciones de la `asignacion_id` activa.

**Supuesto explícito**: esta métrica mide el porcentaje de actividades aprobadas, NO una
"nota final" en el sentido tradicional. El KB no define una fórmula de nota final, y una
media de notas numéricas no funciona cuando hay actividades textuales en el mix.

**Nomenclatura**: el campo se llama `pct_actividades_aprobadas` (no `nota_final` ni
`nota_final_pct`) tanto en el JSON de respuesta como en el encabezado del CSV, para dejar
claro que es un indicador de progreso, no una calificación académica formal.

**Export CSV**: columnas `apellidos`, `nombre`, `comision`, `aprobadas`, `total_actividades`,
`pct_actividades_aprobadas`.

---

## D-C11-7: "Sin corregir" solo aplica a actividades textuales (RN-08)

**Decisión**: la query de "sin corregir" filtra las actividades de `finalizacion_actividad`
con `finalizado=TRUE` a aquellas cuya `actividad` tiene al menos un row en `calificacion`
con `nota_textual IS NOT NULL` para el mismo `(materia_id, asignacion_id)`.

```sql
-- Actividades textuales conocidas (al menos un alumno tiene nota textual)
textual_activities AS (
    SELECT DISTINCT actividad FROM calificacion
    WHERE tenant_id = :t AND materia_id = :m AND asignacion_id = :a
      AND nota_textual IS NOT NULL AND deleted_at IS NULL
),
-- Sin corregir: finalizado=TRUE AND actividad textual AND sin calificacion
sin_corregir AS (
    SELECT fa.entrada_padron_id, fa.actividad
    FROM finalizacion_actividad fa
    WHERE fa.tenant_id = :t AND fa.materia_id = :m AND fa.asignacion_id = :a
      AND fa.finalizado = TRUE AND fa.deleted_at IS NULL
      AND fa.actividad IN (SELECT actividad FROM textual_activities)
      AND NOT EXISTS (
          SELECT 1 FROM calificacion c
          WHERE c.entrada_padron_id = fa.entrada_padron_id
            AND c.actividad = fa.actividad AND c.asignacion_id = :a
            AND c.deleted_at IS NULL
      )
)
```

**Sin finalización importada**: si no hay filas en `finalizacion_actividad` para esa asignacion,
la respuesta es `{ "sin_corregir": [], "aviso": "no_hay_finalizacion_importada" }` — 200 OK
con lista vacía y aviso explícito. No es 404.

---

## D-C11-8: Monitor unificado con scope derivado del rol de la sesión

**Decisión**: un solo endpoint `GET /monitor` con scope automático según permisos:
- PROFESOR/TUTOR: el servicio resuelve sus `asignacion_id`s activas y filtra por ellas.
- COORDINADOR/ADMIN: no hay filtro por asignacion_id (ve todo el tenant).

Los filtros opcionales son idénticos para todos los roles; el scope solo restringe el
universo base. Esto evita mantener dos endpoints casi idénticos (F2.8 vs F2.7/F2.9).

**Query params del monitor**:
- `materia_id` (opcional — solo para COORDINADOR/ADMIN sin sentido para PROFESOR)
- `cohorte_id` (opcional)
- `alumno` (búsqueda libre en nombre/apellidos)
- `comision` (filtro libre de comision en EntradaPadron)
- `regional` (filtro libre de regional en EntradaPadron)
- `estado` (`atrasado` | `al_dia` | todos)
- `fecha_desde`, `fecha_hasta` (rango de fechas — F2.9, aplica a `importado_at` de Calificacion)
- `limit` (default 100, max 500)
- `offset` (default 0)

---

## D-C11-9: `calificaciones:importar` reutilizado para importar-finalizacion

**Decisión**: el endpoint de importación del reporte de finalización (F1.2) usa el permiso
`calificaciones:importar` en lugar de crear un nuevo permiso específico.

**Justificación**: importar el reporte de finalización es semánticamente parte del flujo de
ingesta de datos (Épica 1), y el mismo universo de roles que puede importar calificaciones
debería poder importar el reporte de finalización. Agregar `finalizacion:importar` como permiso
separado no añade control adicional dado que los roles son los mismos.

---

## D-C11-10: Finalizacion parser — vocabulario de "completado" configurable a nivel sistema

**Decisión**: el vocabulario de valores que significan "completado" vive en
`backend/app/core/config.py` como `FINALIZACION_VALORES_COMPLETADO: list[str]` con el
siguiente default (OQ-C11-1 cerrado):

```python
FINALIZACION_VALORES_COMPLETADO: list[str] = Field(
    default=[
        "completado", "completed", "sí", "si", "yes", "true", "1",
        "finalizado", "finished", "done",
    ]
)
```

El parser recibe la lista como parámetro (inyectada desde `settings`), no la hardcodea:

```python
def parse_finalizacion_file(
    content: bytes,
    filename: str,
    valores_completado: list[str] | None = None,
) -> ParsedFinalizacionFile:
    completed = frozenset(v.lower() for v in (valores_completado or DEFAULT_COMPLETED_VALUES))
    ...
```

**Patrón idéntico a RN-02**: `DEFAULT_VALORES_APROBATORIOS` en `calificaciones_service.py`
es un default que se puede sobreescribir con `UmbralMateria.valores_aprobatorios`. Aquí el
override es a nivel sistema (via `settings`), no por tenant por ahora.

**Sin PII en FinalizacionActividad**: el email del archivo de finalización se usa solo para
resolver `entrada_padron_id` (mismo helper `hmac_email` que en C-09 y C-10). El email en
texto plano NO se almacena — solo el UUID `entrada_padron_id`.

## D-C11-11: Permisos — ninguno nuevo (todos ya sembrados en C-04)

**Decisión**: C-11 NO agrega permisos nuevos al seed. Los dos permisos que usa ya existen:

| Permiso | Fuente | Roles que lo tienen |
|---------|--------|---------------------|
| `calificaciones:importar` | C-10 | PROFESOR (own), COORDINADOR (all), ADMIN (all) |
| `atrasados:ver` | C-04 | TUTOR (all), PROFESOR (own), COORDINADOR (all), ADMIN (all) |
| `entregas:detectar_sin_corregir` | C-04 | TUTOR (all), PROFESOR (own), COORDINADOR (all), ADMIN (all) |

**Asignación de permisos por endpoint**:
- `importar-finalizacion` → `calificaciones:importar` (es import de datos, épica 1)
- `atrasados`, `ranking`, `reportes-rapidos`, `notas-finales`, monitor → `atrasados:ver`
- `sin-corregir` → `entregas:detectar_sin_corregir` (permiso específico de RN-07/08)

**Scope de TUTOR**: según el seed (fiel al KB §3.3), TUTOR tiene `atrasados:ver` scope=`all`
y `entregas:detectar_sin_corregir` scope=`all` (sin "(propio)" en la matriz del KB).
El service debe tratar el scope de TUTOR como "todos los alumnos del tenant para su contexto"
(no filtrado por asignacion propia).

---

## Migración 009 — Resumen

```
revision = "e8f9a0b1c2d3_009_finalizacion_actividad"
down_revision = "d7e8f9a0b1c2"  ← C-10 (008_calificacion_umbral_materia)

upgrade():
  op.create_table("finalizacion_actividad",
    id UUID PK,
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    entrada_padron_id UUID FK→entrada_padron RESTRICT NOT NULL,
    materia_id UUID FK→materia RESTRICT NOT NULL,
    asignacion_id UUID FK→asignacion RESTRICT NOT NULL,
    actividad VARCHAR(500) NOT NULL,
    finalizado BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
  )
  # trigger updated_at
  # Unicidad: un alumno no puede tener dos filas para la misma actividad bajo la misma asignación
  CREATE UNIQUE INDEX uq_finalizacion_entrada_actividad_asignacion
    ON finalizacion_actividad (entrada_padron_id, actividad, asignacion_id)
    WHERE deleted_at IS NULL;
  # Para el cruce con calificacion (RN-07/08):
  CREATE INDEX idx_finalizacion_materia_asignacion
    ON finalizacion_actividad (tenant_id, materia_id, asignacion_id)
    WHERE deleted_at IS NULL AND finalizado = TRUE;
  CREATE INDEX idx_finalizacion_entrada_padron
    ON finalizacion_actividad (entrada_padron_id)
    WHERE deleted_at IS NULL;

downgrade():
  op.drop_table("finalizacion_actividad")
```
