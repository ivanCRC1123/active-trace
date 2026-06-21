"""Router C-13 guardias (F6.6).

POST   /api/v1/guardias              — registrar guardia propia
GET    /api/v1/guardias              — listar guardias (scoped por rol)
PATCH  /api/v1/guardias/{guardia_id} — editar estado/comentarios
GET    /api/v1/guardias/export       — export CSV (COORDINADOR/ADMIN only)

RBAC: guardias:registrar
  scope="own" → TUTOR, PROFESOR (registran y ven solo las propias)
  scope="all" → COORDINADOR, ADMIN (ven todo el tenant + pueden exportar)
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.guardias import GuardiaCreate, GuardiaResponse, GuardiaUpdate
from app.services.guardia_service import GuardiaService

router = APIRouter(prefix="/api/v1/guardias", tags=["guardias"])

_PERM = require_permission("guardias:registrar", scoped=True)


def _svc(db: AsyncSession) -> GuardiaService:
    return GuardiaService(db)


def _handle(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "no_encontrad" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "no_propi" in msg or "export_requiere" in msg:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=msg)


@router.post("/", response_model=GuardiaResponse, status_code=status.HTTP_201_CREATED)
async def registrar(
    data: GuardiaCreate,
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> GuardiaResponse:
    current_user, scope = auth
    try:
        return await _svc(db).registrar(current_user, data, scope)
    except (ValueError, PermissionError, LookupError) as exc:
        raise _handle(exc)


@router.get("/export")
async def exportar_csv(
    materia_id: Optional[UUID] = Query(default=None),
    carrera_id: Optional[UUID] = Query(default=None),
    cohorte_id: Optional[UUID] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> Response:
    current_user, scope = auth
    try:
        csv_str = await _svc(db).exportar_csv(
            current_user, scope, materia_id, carrera_id, cohorte_id, estado, fecha_desde, fecha_hasta
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=guardias.csv"},
    )


@router.get("/", response_model=list[GuardiaResponse])
async def listar(
    materia_id: Optional[UUID] = Query(default=None),
    carrera_id: Optional[UUID] = Query(default=None),
    cohorte_id: Optional[UUID] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
    asignacion_id: Optional[UUID] = Query(default=None),
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> list[GuardiaResponse]:
    current_user, scope = auth
    return await _svc(db).listar(
        current_user, scope, materia_id, carrera_id, cohorte_id, estado,
        fecha_desde, fecha_hasta, asignacion_id
    )


@router.patch("/{guardia_id}", response_model=GuardiaResponse)
async def editar(
    guardia_id: UUID,
    data: GuardiaUpdate,
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> GuardiaResponse:
    current_user, scope = auth
    try:
        return await _svc(db).editar(current_user, guardia_id, data, scope)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
