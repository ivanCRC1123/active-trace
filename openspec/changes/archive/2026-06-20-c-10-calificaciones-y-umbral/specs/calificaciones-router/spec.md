# Spec: Router de Calificaciones

Archivo: `backend/app/api/v1/routers/calificaciones.py`

## Endpoints

### POST `/api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}/importar`

**Guard**: `calificaciones:importar`

**Request**: `multipart/form-data`
- `archivo: UploadFile` — archivo xlsx del LMS
- `actividades: str` — JSON array de nombres de columnas a importar (omitir o `[]` → modo preview)

**Lógica**:
```
si actividades es None o lista vacía:
    → modo PREVIEW: parsear xlsx, retornar CalificacionesPreview (HTTP 200)
    → NO escribe en DB
si actividades tiene al menos un elemento:
    → modo CONFIRM: importar solo las columnas listadas → HTTP 201 CalificacionesImportResult
    → Valida: existe VersionPadron activa → 409 si no
    → Valida: materia en tenant → 404 si no
    → Calcula aprobado con UmbralMateria del docente (o defaults)
    → Upsert calificaciones
    → Audit: CALIFICACIONES_IMPORTAR
```

**Error codes**:
| Condición | HTTP |
|-----------|------|
| Archivo no xlsx/csv | 400 `archivo_invalido` |
| Sin columna email detectable | 400 `sin_columna_email` |
| No hay VersionPadron activa | 409 `no_hay_padron_activo` |
| `actividades` lista con nombres inválidos | 400 `actividad_invalida` |
| Materia no en tenant | 404 |
| Sin permiso | 403 |

---

### POST `/api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}/importar-finalizacion`

**Guard**: `calificaciones:importar`

**Request**: `multipart/form-data`
- `archivo: UploadFile` — reporte de finalización exportado del LMS

**Respuesta**: `200 FinalizacionResult`

**Lógica**:
```
1. Parsear archivo de finalización: detectar alumnos con actividades en estado "Finalizado"
2. Cruzar con Calificaciones existentes para la materia+asignación actual
3. Actividades textuales finalizadas pero sin Calificacion → "sin corregir" (RN-07, RN-08)
4. Actividades numéricas NO se incluyen (RN-08)
```

**NO escribe en DB** — solo retorna el análisis.

---

### GET `/api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}`

**Guard**: `calificaciones:ver`

**Query params**:
- `actividad: str` (opcional) — filtrar por actividad específica
- `solo_aprobados: bool` (opcional) — filtrar por aprobado=True
- `solo_reprobados: bool` (opcional) — filtrar por aprobado=False

**Respuesta**: `200 CalificacionesPorAlumno`

**Scope**:
- scope=own: devuelve calificaciones con `asignacion_id = asignacion_actual del usuario`.
- scope=all: devuelve todas las calificaciones de la materia en el tenant.

---

### DELETE `/api/v1/calificaciones/{materia_id}/cohortes/{cohorte_id}/vaciar`

**Guard**: `calificaciones:importar`

**Respuesta**: `204 No Content`

**Lógica**:
```
si scope=own:
    asignacion = get_asignacion_activa(current_user, materia_id)
    si no existe asignacion → 403 "sin_asignacion_activa"
    soft_delete WHERE asignacion_id = asignacion.id AND materia_id = materia_id
si scope=all:
    soft_delete WHERE materia_id = materia_id AND tenant_id = tenant_id
```

---

### GET `/api/v1/umbral/{materia_id}`

**Guard**: `calificaciones:importar`

**Respuesta**: `200 UmbralMateriaResponse`

**Lógica**:
```
asignacion = get_asignacion_activa(current_user, materia_id)
si no existe → 404 "sin_asignacion_activa"
umbral = UmbralMateriaRepository.get_by_asignacion_materia(asignacion.id, materia_id)
si umbral es None → retornar defaults con es_default=True
sino → retornar umbral con es_default=False
```

---

### PUT `/api/v1/umbral/{materia_id}`

**Guard**: `calificaciones:importar`

**Request body**: `UmbralMateriaRequest` (JSON)

**Respuesta**: `200 UmbralMateriaResponse`

**Lógica**:
```
asignacion = get_asignacion_activa(current_user, materia_id)
si no existe → 404 "sin_asignacion_activa"
UmbralMateriaRepository.upsert(asignacion.id, materia_id, data.umbral_pct, data.valores_aprobatorios)
retornar UmbralMateriaResponse con es_default=False
```

## Helper: get_asignacion_activa

```python
async def _get_asignacion_activa(
    current_user: CurrentUser,
    materia_id: UUID,
    session: AsyncSession,
) -> Asignacion | None:
    """Busca la asignación vigente del usuario actual en la materia dada."""
    today = date.today()
    result = await session.execute(
        select(Asignacion).where(
            Asignacion.tenant_id == current_user.tenant_id,
            Asignacion.usuario_id == current_user.user_id,
            Asignacion.materia_id == materia_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        )
    )
    return result.scalar_one_or_none()
```

## Permisos en seed

```python
# scripts/seed_permissions.py — agregar al final:
{"codigo": "calificaciones:importar", "modulo": "calificaciones",
 "roles": [
    {"nombre": "PROFESOR",     "scope": "own"},
    {"nombre": "COORDINADOR",  "scope": "all"},
    {"nombre": "ADMIN",        "scope": "all"},
 ]},
{"codigo": "calificaciones:ver", "modulo": "calificaciones",
 "roles": [
    {"nombre": "PROFESOR",     "scope": "own"},
    {"nombre": "TUTOR",        "scope": "own"},
    {"nombre": "COORDINADOR",  "scope": "all"},
    {"nombre": "ADMIN",        "scope": "all"},
 ]},
```

## Manejo de errores en el Router

```python
def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg == "no_hay_padron_activo":  return HTTPException(409, detail=msg)
    if msg == "sin_asignacion_activa": return HTTPException(404, detail=msg)
    if msg in ("materia_not_found", "cohorte_not_found"): return HTTPException(404, detail=msg)
    if msg in ("archivo_invalido", "sin_columna_email", "actividad_invalida"):
        return HTTPException(400, detail=msg)
    return HTTPException(400, detail=msg)
```
