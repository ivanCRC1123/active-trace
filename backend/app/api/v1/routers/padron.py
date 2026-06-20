"""Padrón endpoints — student roster ingestion (C-09).

Permissions:
  padron:cargar — import file, Moodle sync, vaciar
  padron:ver    — read active padrón + entries

Prefix: /api/v1/padron
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_moodle_client
from app.core.permissions import require_permission
from app.integrations.moodle_ws import MoodleWSClientProtocol, MoodleWSError
from app.schemas.auth import CurrentUser
from app.schemas.padron import PadronConEntradas, PadronImportResult, PadronPreview
from app.services.padron_service import PadronService

router = APIRouter(prefix="/api/v1/padron", tags=["padron"])

_PERM_CARGAR = require_permission("padron:cargar")
_PERM_VER = require_permission("padron:ver")


def _svc(db: AsyncSession) -> PadronService:
    return PadronService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg in ("materia_not_found", "cohorte_not_found", "padron_not_found"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if msg == "padron_no_autorizado":
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no tenés permiso para vaciar versiones cargadas por otros usuarios",
        )
    if msg == "moodle_no_configurado":
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="integración Moodle no configurada",
        )
    if msg == "materia_sin_moodle_course_id":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="la materia no tiene moodle_course_id configurado",
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/{materia_id}/cohortes/{cohorte_id}/importar",
    status_code=status.HTTP_201_CREATED,
)
async def importar_padron(
    materia_id: UUID,
    cohorte_id: UUID,
    file: UploadFile = File(...),
    preview: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_CARGAR),
) -> PadronImportResult | PadronPreview:
    current_user, _ = perm
    content = await file.read()
    filename = file.filename or "upload"
    try:
        result = await _svc(db).import_from_file(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            content=content,
            filename=filename,
            preview=preview,
        )
    except ValueError as exc:
        raise _http(exc)

    if preview:
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result.model_dump(mode="json"),
        )
    return result


@router.post(
    "/{materia_id}/cohortes/{cohorte_id}/sincronizar-moodle",
    response_model=PadronImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def sincronizar_moodle(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    moodle_client: MoodleWSClientProtocol = Depends(get_moodle_client),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_CARGAR),
) -> PadronImportResult:
    current_user, _ = perm
    try:
        return await _svc(db).import_from_moodle(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            moodle_client=moodle_client,
        )
    except MoodleWSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": str(exc), "retry": True},
        )
    except ValueError as exc:
        raise _http(exc)


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}",
    response_model=PadronConEntradas,
)
async def get_padron(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> PadronConEntradas:
    current_user, _ = perm
    result = await _svc(db).get_padron_activo(
        materia_id=materia_id,
        cohorte_id=cohorte_id,
        tenant_id=current_user.tenant_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no hay padrón activo para esta materia y cohorte",
        )
    return result


@router.delete(
    "/{materia_id}/cohortes/{cohorte_id}/vaciar",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def vaciar_padron(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_CARGAR),
) -> Response:
    current_user, scope = perm
    try:
        await _svc(db).vaciar(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            perm_scope=scope or "own",
        )
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
