# C-10 — Design Decisions

## D-C10-1: `aprobado` se calcula al importar y se persiste (computed-at-write)

**Decisión**: el campo `aprobado` de `Calificacion` se calcula en el servicio en el momento
de la importación y se almacena como booleano en la DB. No se recalcula en cada query.

**Justificación**:
- C-11 (atrasados) hace queries masivos `WHERE aprobado = FALSE`. Si `aprobado` fuera virtual,
  cada query recalcularía contra el umbral → inaceptable a escala.
- El umbral rara vez cambia. Si cambia, el docente re-importa el archivo para actualizar.
- La semántica de "derivado" en el KB describe la *regla de cálculo*, no que el campo sea
  virtual. El modelo de la DB necesita el valor materializado para queries eficientes.

**Fórmula** (ver OQ-C10-1 para la pregunta sobre escala):
```python
def _calcular_aprobado(
    nota_numerica: Decimal | None,
    nota_textual: str | None,
    umbral_pct: int,
    valores_aprobatorios: list[str],
) -> bool:
    if nota_numerica is not None:
        return nota_numerica >= Decimal(umbral_pct)  # escala 0-100
    if nota_textual is not None:
        return nota_textual in valores_aprobatorios
    return False  # sin nota de ningún tipo → no aprobado
```

**Cuándo se recalcula**: solo al re-importar. El docente debe re-importar si cambia el umbral
y quiere que `aprobado` refleje el nuevo criterio.

---

## D-C10-2: `asignacion_id` en Calificacion (scope isolation, RN-04)

**Decisión**: `Calificacion` lleva un FK `asignacion_id → asignacion` (nullable, RESTRICT).

**Justificación**:
- RN-04: "La operación de vaciado elimina únicamente los datos del usuario que la ejecuta
  en esa materia." El scope de los datos importados es `(usuario_id × materia_id)`, que en
  el modelo de dominio corresponde a una Asignacion.
- Permite a PROFESOR (scope=own) acceder/vaciar solo `calificaciones WHERE asignacion_id = su_asignacion`.
- Permite al sistema derivar el umbral correcto: `UmbralMateria` también tiene `asignacion_id`,
  por lo que la derivación de `aprobado` usa el umbral del docente que importó.
- COORDINADOR/ADMIN (scope=all) accede a todas las calificaciones de la materia.

**Nullable**: en el edge case de importación manual o futura integración directa,
`asignacion_id` puede ser NULL. Los queries de scope=own filtran `asignacion_id = ?`; los
queries de scope=all no filtran por `asignacion_id`.

---

## D-C10-3: UmbralMateria es upsert (no versionado)

**Decisión**: hay exactamente un `UmbralMateria` activo por `(asignacion_id, materia_id)`. Al
actualizar el umbral se actualiza el mismo registro. No se versiona el historial del umbral.

**Justificación**:
- El KB no menciona versionado de umbral. La regla es configuración operativa del docente.
- El historial del umbral en el momento de cada importación queda implícito en `aprobado`
  (computed-at-write, D-C10-1).
- Versionar el umbral complicaría C-11 sin beneficio funcional inmediato.

**Índice único**: `UNIQUE INDEX uq_umbral_asignacion_materia ON umbral_materia(asignacion_id, materia_id) WHERE deleted_at IS NULL`.

---

## D-C10-4: Import en dos pasos — detect-preview + confirm con selección

**Decisión**: el import de calificaciones sigue el mismo patrón preview/confirm que C-09, pero
con una selección explícita de actividades entre los dos pasos.

```
1. POST .../importar (multipart archivo)          → 200 CalificacionesPreview
   { actividades_detectadas: [{nombre, tipo, total_notas}],
     alumnos_detectados: N,
     warnings: [...] }

2. POST .../importar (multipart archivo + JSON actividades=[...])  → 201 CalificacionesImportResult
   { actividades_importadas: N, calificaciones_creadas: N, aprobadas: K, advertencias: [...] }
```

**Diseño del request**:
- La UI hace dos llamadas al mismo endpoint diferenciadas por el body:
  - Primera llamada: sin campo `actividades` → modo preview (detección, sin DB write).
  - Segunda llamada: con campo `actividades` → modo confirm (escribe en DB).
- Esto evita tener que manejar estado de sesión entre preview y confirm.

**Selección de actividades**:
- El parser detecta TODAS las columnas que parecen actividades.
- El usuario selecciona un subconjunto (lista de nombres de columna).
- Solo se importan las calificaciones de las columnas seleccionadas.
- Si `actividades` está vacía → error 400 ("debe seleccionar al menos una actividad").

---

## D-C10-5: Sin padrón activo → 409 (no 400)

**Decisión**: intentar importar calificaciones cuando no existe un `VersionPadron` activo para
`(tenant_id, materia_id, cohorte_id)` retorna HTTP **409 Conflict** con
`detail="no_hay_padron_activo"`.

**Justificación**:
- HTTP 400 indica request malformado. Aquí el request es válido; el problema es el estado del
  sistema (falta el padrón). 409 comunica "conflict with current state of the resource".
- Permite al cliente diferenciar entre "el archivo es inválido" (400) y "hay que importar
  el padrón primero" (409).

---

## D-C10-6: Vaciar calificaciones = soft-delete masivo por asignacion_id

**Decisión**: `DELETE /calificaciones/.../vaciar` hace soft-delete de todas las `Calificacion`
con `asignacion_id = asignacion_actual AND materia_id = materia_id AND deleted_at IS NULL`.
No soft-delete el UmbralMateria (el criterio de aprobación se conserva).

**Scope (RN-04)**:
- PROFESOR (scope=own): `asignacion_id` = su asignación activa en esa materia. Si no tiene
  asignación activa → 403.
- COORDINADOR/ADMIN (scope=all): vacía todas las `Calificacion` de `materia_id` en el tenant
  (sin filtrar por asignacion_id).

---

## D-C10-7: Columnas de identificación del alumno en el xlsx del LMS

**Decisión**: el parser de calificaciones identifica al alumno en el xlsx buscando una columna
con la dirección de email usando los mismos alias que `padron_parser.py`:
`["email", "correo", "mail", "e-mail", "e mail", "dirección de correo electrónico",
"email address"]`.

El alumno se vincula con una `EntradaPadron` por `email_hash`. Si no hay match en el padrón
activo, la fila se descarta con un warning (no es un error — el padrón puede estar
desactualizado).

```python
async def _resolve_entrada_padron(email: str, materia_id, cohorte_id, tenant_id, session):
    h = hmac_email(email)
    result = await session.execute(
        select(EntradaPadron)
        .join(VersionPadron, EntradaPadron.version_id == VersionPadron.id)
        .where(
            VersionPadron.tenant_id == tenant_id,
            VersionPadron.materia_id == materia_id,
            VersionPadron.cohorte_id == cohorte_id,
            VersionPadron.activa == True,
            VersionPadron.deleted_at.is_(None),
            EntradaPadron.email_hash == h,
            EntradaPadron.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
```

**Sin columna email → 400**: si el archivo no tiene columna identificable como email,
el import falla con 400 ("archivo inválido — no se encontró columna de email").

---

## D-C10-8: `valores_aprobatorios` — default centralizado en el servicio

**Decisión**: el default de `valores_aprobatorios` (["Satisfactorio", "Supera lo esperado"])
vive en el servicio, no en el modelo. Si `UmbralMateria` no existe para la asignación,
`CalificacionesService` usa los defaults sin necesidad de leer de la DB.

```python
DEFAULT_UMBRAL_PCT = 60
DEFAULT_VALORES_APROBATORIOS = ["Satisfactorio", "Supera lo esperado"]

async def _get_umbral(asignacion_id, materia_id, session) -> tuple[int, list[str]]:
    umbral = await UmbralMateriaRepository(...).get_by_asignacion_materia(asignacion_id, materia_id)
    if umbral is None:
        return DEFAULT_UMBRAL_PCT, DEFAULT_VALORES_APROBATORIOS
    return umbral.umbral_pct, umbral.valores_aprobatorios
```

---

## Migración 008 — Resumen

```
revision = "b2c3d4e5f6a7_008_calificacion_umbral"
down_revision = "a1b2c3d4e5f6"   ← migración 007 (C-09)

upgrade():
  op.create_table("umbral_materia",
    id UUID PK,
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    asignacion_id UUID FK→asignacion RESTRICT NOT NULL,
    materia_id UUID FK→materia RESTRICT NOT NULL,
    umbral_pct INTEGER NOT NULL DEFAULT 60,
    valores_aprobatorios JSONB NOT NULL DEFAULT '["Satisfactorio", "Supera lo esperado"]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
  )
  # trigger updated_at en umbral_materia
  CREATE UNIQUE INDEX uq_umbral_asignacion_materia
    ON umbral_materia (asignacion_id, materia_id)
    WHERE deleted_at IS NULL;
  CREATE INDEX idx_umbral_materia_tenant ON umbral_materia(tenant_id) WHERE deleted_at IS NULL;

  op.create_table("calificacion",
    id UUID PK,
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    entrada_padron_id UUID FK→entrada_padron RESTRICT NOT NULL,
    materia_id UUID FK→materia RESTRICT NOT NULL,
    asignacion_id UUID FK→asignacion RESTRICT NULL,  # nullable: scope isolation
    actividad VARCHAR(500) NOT NULL,
    nota_numerica NUMERIC(7,2) NULL,
    nota_textual VARCHAR(255) NULL,
    aprobado BOOLEAN NOT NULL,
    origen VARCHAR(20) NOT NULL DEFAULT 'Importado',  # 'Importado' | 'Manual'
    importado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
  )
  # trigger updated_at en calificacion
  # Índice para queries de atrasados (C-11):
  CREATE INDEX idx_calificacion_entrada_padron
    ON calificacion(entrada_padron_id) WHERE deleted_at IS NULL;
  CREATE INDEX idx_calificacion_materia_asignacion
    ON calificacion(tenant_id, materia_id, asignacion_id) WHERE deleted_at IS NULL;
  CREATE INDEX idx_calificacion_aprobado
    ON calificacion(tenant_id, materia_id, aprobado) WHERE deleted_at IS NULL;
  # Unicidad: un alumno no puede tener dos calificaciones para la misma actividad
  # bajo la misma asignación (permite re-importar como upsert):
  CREATE UNIQUE INDEX uq_calificacion_entrada_actividad_asignacion
    ON calificacion (entrada_padron_id, actividad, asignacion_id)
    WHERE deleted_at IS NULL;

downgrade():
  op.drop_table("calificacion")
  op.drop_table("umbral_materia")
```

---

## Open Questions para C-10

| ID | Pregunta | Propuesta de resolución | Bloquea |
|----|----------|------------------------|---------|
| OQ-C10-1 | ¿El LMS exporta notas en escala 0–100 o 0–10? | El archivo xlsx de Moodle con sufijo `(Real)` exporta en porcentaje (0.00–100.00). Asumir 0–100 hasta confirmar con datos reales. | Fórmula de `aprobado` |
| OQ-C10-2 | ¿Re-calcular `aprobado` al cambiar umbral? | No recalcular automáticamente — el docente re-importa. Documentar el comportamiento en la UI (C-22). | UX |
| OQ-C10-3 | ¿El "reporte de finalización" es un archivo separado o una detección en el mismo xlsx? | Implementar como endpoint separado `importar-finalizacion`. El usuario sube el segundo archivo. Permite flujo independiente. | Endpoint design |
