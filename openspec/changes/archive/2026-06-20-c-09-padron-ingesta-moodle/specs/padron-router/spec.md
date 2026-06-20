# Spec: Padron Router

## Endpoints

Base prefix: `/api/v1/padron`

Todos los endpoints requieren JWT válido (`get_current_user`). El `tenant_id` se extrae del JWT
(nunca de la URL ni del body).

---

### POST `/api/v1/padron/{materia_id}/cohortes/{cohorte_id}/importar`

**Propósito**: importar padrón desde archivo xlsx/csv.

**Guard**: `require_permission("padron:cargar")`

**Request**:
```
Content-Type: multipart/form-data
Fields:
  - file: UploadFile (xlsx o csv)
Query:
  - preview: bool = False
```

**Response `200` (preview=true)**:
```json
{
  "total": 25,
  "vinculados": 8,
  "advertencias": ["fila 3: comisión vacía"],
  "entradas": [
    { "nombre": "Ana", "apellidos": "García", "comision": "A", "regional": null, "vinculado": true }
  ]
}
```

**Response `201` (preview=false, import exitoso)**:
```json
{
  "version": { "id": "...", "materia_id": "...", "cohorte_id": "...", "activa": true, ... },
  "total_importadas": 25,
  "entradas_vinculadas": 8,
  "advertencias": []
}
```

**Errores**:
- `400` si el archivo no tiene columnas de email reconocidas.
- `400` si el archivo está vacío o tiene formato inválido.
- `403` si el usuario no tiene `padron:cargar`.
- `404` si `materia_id` o `cohorte_id` no existen en el tenant.

**Implementación del scope propio (PROFESOR)**:
El servicio verifica que la materia_id aparezca en las asignaciones vigentes del usuario
(vía `AsignacionRepository`). Si el PROFESOR no está asignado a esa materia → 403.
El COORDINADOR (scope=all) puede importar en cualquier materia del tenant.

---

### POST `/api/v1/padron/{materia_id}/cohortes/{cohorte_id}/sincronizar-moodle`

**Propósito**: disparar sync on-demand desde Moodle WS para la materia indicada.

**Guard**: `require_permission("padron:cargar")`

**Request**: sin body.

**Response `201`**: igual que import exitoso (PadronImportResult).

**Errores**:
- `400` si `materia.moodle_course_id` no está configurado.
- `502` si `MoodleWSError` es lanzado por el cliente. Body: `{"detail": "Moodle WS no disponible", "retry": true}`.
- `503` si `MOODLE_BASE_URL` no está configurado en settings.
- `403`, `404` iguales que import archivo.

---

### GET `/api/v1/padron/{materia_id}/cohortes/{cohorte_id}`

**Propósito**: devolver la versión activa del padrón con todas sus entradas.

**Guard**: `require_permission("padron:ver")`

**Response `200`**:
```json
{
  "version": {
    "id": "...",
    "materia_id": "...",
    "cohorte_id": "...",
    "cargado_por": "...",
    "cargado_at": "2026-06-20T10:00:00Z",
    "activa": true,
    "total_entradas": 25,
    "entradas_vinculadas": 8
  },
  "entradas": [
    {
      "id": "...", "version_id": "...", "usuario_id": "...",
      "nombre": "Ana", "apellidos": "García",
      "email": "ana@uni.edu",
      "comision": "A", "regional": "Norte",
      "vinculado": true
    }
  ]
}
```

**Errores**:
- `404` si no hay versión activa para `(materia_id, cohorte_id)` en el tenant.
- `404` si `materia_id` o `cohorte_id` no existen en el tenant.

---

### DELETE `/api/v1/padron/{materia_id}/cohortes/{cohorte_id}/vaciar`

**Propósito**: vaciar el padrón activo (scope-isolated por RN-04).

**Guard**: `require_permission("padron:cargar")`

**Request**: sin body.

**Response `204`**: sin cuerpo.

**Lógica de scope**:
```python
version = await repo.get_active(materia_id, cohorte_id)
if version is None:
    raise HTTPException(404, "no hay padrón activo")

# Scope check para PROFESOR (scope=own):
perm = await check_permission(current_user.user_id, tenant_id, "padron:cargar", session)
if perm.scope == "own" and version.cargado_por != current_user.user_id:
    raise HTTPException(403, "no tenés permiso para vaciar versiones cargadas por otros usuarios")

# Soft-delete version (D-C09-6)
version.activa = False
version.deleted_at = datetime.now(timezone.utc)
await session.commit()
```

**Errores**:
- `403` si scope=own y la versión activa no fue cargada por el usuario autenticado.
- `404` si no hay versión activa.

---

## Router implementation

```python
# backend/app/api/v1/routers/padron.py

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_moodle_client
from app.core.permissions import require_permission
from app.integrations.moodle_ws import MoodleWSClientProtocol, MoodleWSError
from app.schemas.auth import CurrentUser
from app.schemas.padron import PadronImportResult, PadronPreview, VersionPadronResponse
from app.services.padron_service import PadronService

router = APIRouter(prefix="/api/v1/padron", tags=["padron"])

_PERM_CARGAR = require_permission("padron:cargar")
_PERM_VER = require_permission("padron:ver")


def _svc(db: AsyncSession) -> PadronService:
    return PadronService(db)


@router.post("/{materia_id}/cohortes/{cohorte_id}/importar", status_code=status.HTTP_201_CREATED)
async def importar_padron(
    materia_id: UUID,
    cohorte_id: UUID,
    file: UploadFile = File(...),
    preview: bool = Query(default=False),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_PERM_CARGAR),
) -> PadronImportResult | PadronPreview:
    ...


@router.post("/{materia_id}/cohortes/{cohorte_id}/sincronizar-moodle", status_code=status.HTTP_201_CREATED)
async def sincronizar_moodle(
    materia_id: UUID,
    cohorte_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    moodle_client: MoodleWSClientProtocol = Depends(get_moodle_client),
    _: None = Depends(_PERM_CARGAR),
) -> PadronImportResult:
    try:
        return await _svc(db).import_from_moodle(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            tenant_id=current_user.tenant_id,
            cargado_por=current_user.user_id,
            moodle_client=moodle_client,
        )
    except MoodleWSError as exc:
        raise HTTPException(502, detail={"detail": str(exc), "retry": True})


@router.get("/{materia_id}/cohortes/{cohorte_id}")
async def get_padron(
    materia_id: UUID,
    cohorte_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_PERM_VER),
) -> ...:
    ...


@router.delete("/{materia_id}/cohortes/{cohorte_id}/vaciar", status_code=status.HTTP_204_NO_CONTENT)
async def vaciar_padron(
    materia_id: UUID,
    cohorte_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_PERM_CARGAR),
) -> None:
    ...
```

## Registro en main.py

```python
from app.api.v1.routers import padron
app.include_router(padron.router)
```

## RBAC — permisos a seedear

```python
# Agregar en scripts/seed_permissions.py (o scripts/seed_rbac.py según implementación actual):
NUEVOS_PERMISOS = [
    {"codigo": "padron:cargar", "modulo": "padron", "descripcion": "Importar y gestionar padrón"},
    {"codigo": "padron:ver",    "modulo": "padron", "descripcion": "Consultar padrón activo"},
]

NUEVAS_ASIGNACIONES = [
    # PROFESOR: scope=own (solo sus materias, verificado en el servicio)
    ("PROFESOR", "padron:cargar", "own"),
    ("PROFESOR", "padron:ver",    "own"),
    # COORDINADOR y ADMIN: scope=all
    ("COORDINADOR", "padron:cargar", "all"),
    ("COORDINADOR", "padron:ver",    "all"),
    ("ADMIN",       "padron:cargar", "all"),
    ("ADMIN",       "padron:ver",    "all"),
]
```
