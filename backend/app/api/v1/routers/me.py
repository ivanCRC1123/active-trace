"""Endpoints sobre el usuario autenticado (C-22).

No requieren permiso especial — solo un JWT válido.
Prefix: /api/v1/me
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.asignaciones import MeAsignacionItem
from app.schemas.auth import CurrentUser
from app.services.asignacion_service import AsignacionService

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("/asignaciones", response_model=list[MeAsignacionItem])
async def get_mis_asignaciones(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MeAsignacionItem]:
    """Devuelve las asignaciones vigentes del usuario autenticado."""
    return await AsignacionService(db).list_mis_asignaciones(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
    )
