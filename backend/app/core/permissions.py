"""Permission resolution module — RBAC query layer.

Provides functions to resolve effective permissions from UserRol → Rol
→ RolPermiso → Permiso, with soft-delete filtering and scope resolution.

All functions are stateless and accept an async session explicitly —
they can be used from services, dependencies, or scripts.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.user_rol import UserRol


class PermissionCheck(BaseModel):
    """Result of a permission check.

    Attributes:
        granted: Whether the permission is granted.
        scope: The scope of the permission (``"all"`` or ``"own"``)
               or ``None`` if not granted.
    """

    model_config = ConfigDict(extra="forbid")

    granted: bool
    scope: str | None = None


async def get_user_permissions(
    user_id: UUID,
    tenant_id: UUID,
    session: AsyncSession,
) -> dict[str, str]:
    """Resolve all effective permissions for a user.

    Computes the union of permissions from all active roles assigned
    to the user. If the same permission appears with both ``"all"``
    and ``"own"`` scopes from different roles, ``"all"`` wins.

    Args:
        user_id: The user's UUID.
        tenant_id: The tenant's UUID.
        session: An async SQLAlchemy session.

    Returns:
        A dict mapping permission code → effective scope.
        Empty dict if the user has no permissions.
    """
    stmt = (
        select(Permiso.codigo, RolPermiso.scope)
        .select_from(UserRol)
        .join(Rol, Rol.id == UserRol.rol_id)
        .join(RolPermiso, RolPermiso.rol_id == Rol.id)
        .join(Permiso, Permiso.id == RolPermiso.permiso_id)
        .where(
            UserRol.user_id == user_id,
            UserRol.tenant_id == tenant_id,
            UserRol.deleted_at.is_(None),
            Rol.deleted_at.is_(None),
            RolPermiso.deleted_at.is_(None),
            Permiso.deleted_at.is_(None),
        )
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Build effective permissions: union of all roles, 'all' wins over 'own'
    effective: dict[str, str] = {}
    for codigo, scope in rows:
        if codigo not in effective or (scope == "all" and effective[codigo] == "own"):
            effective[codigo] = scope
    return effective


async def check_permission(
    user_id: UUID,
    tenant_id: UUID,
    permission_codigo: str,
    session: AsyncSession,
) -> PermissionCheck:
    """Check if a user has a specific permission.

    Args:
        user_id: The user's UUID.
        tenant_id: The tenant's UUID.
        permission_codigo: The permission code to check
                           (e.g., ``"calificaciones:importar"``).
        session: An async SQLAlchemy session.

    Returns:
        A ``PermissionCheck`` with ``granted`` and ``scope``.
    """
    stmt = (
        select(RolPermiso.scope)
        .select_from(UserRol)
        .join(Rol, Rol.id == UserRol.rol_id)
        .join(RolPermiso, RolPermiso.rol_id == Rol.id)
        .join(Permiso, Permiso.id == RolPermiso.permiso_id)
        .where(
            UserRol.user_id == user_id,
            UserRol.tenant_id == tenant_id,
            UserRol.deleted_at.is_(None),
            Rol.deleted_at.is_(None),
            RolPermiso.deleted_at.is_(None),
            Permiso.deleted_at.is_(None),
            Permiso.codigo == permission_codigo,
        )
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return PermissionCheck(granted=False, scope=None)

    # If any role grants 'all', that's the effective scope
    scopes = {row[0] for row in rows}
    if "all" in scopes:
        return PermissionCheck(granted=True, scope="all")
    return PermissionCheck(granted=True, scope="own")


# ── FastAPI Dependency Guard ─────────────────────────────────────────


def require_permission(permission: str, scoped: bool = False):
    """FastAPI dependency factory — checks if the current user has a permission.

    Args:
        permission: The required permission code (e.g., ``"calificaciones:importar"``).
        scoped: If ``True``, returns a ``(CurrentUser, scope | None)`` tuple
                so the endpoint can enforce resource-level restrictions.

    Returns:
        A FastAPI dependency callable that injects a ``(CurrentUser, scope | None)``
        tuple or raises HTTP 403.

    Usage::

        @router.get("/some-resource")
        async def handler(
            _: tuple[CurrentUser, str | None] = Depends(
                require_permission("modulo:accion", scoped=True)
            ),
        ):
            current_user, scope = _
    """
    from fastapi import Depends, HTTPException, status  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: PLC0415

    from app.core.dependencies import get_current_user, get_db  # noqa: PLC0415
    from app.schemas.auth import CurrentUser  # noqa: PLC0415

    async def _check(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[CurrentUser, str | None]:
        check = await check_permission(
            current_user.user_id,
            current_user.tenant_id,
            permission,
            db,
        )
        if not check.granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return current_user, check.scope if scoped else None

    return _check
