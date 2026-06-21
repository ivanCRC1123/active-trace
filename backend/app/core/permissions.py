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


async def _resolve_effective_permissions(
    user_id: UUID,
    tenant_id: UUID,
    session: AsyncSession,
) -> dict[str, str]:
    """Single source of truth for RBAC resolution.

    Executes the UserRol → Rol → RolPermiso → Permiso JOIN for all active
    role assignments of the user and accumulates the effective permission map.
    Rule: if the same permission appears in multiple roles with different scopes,
    ``"all"`` wins over ``"own"``.

    Returns a dict mapping permission code → effective scope.
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

    effective: dict[str, str] = {}
    for codigo, scope in result.all():
        if codigo not in effective or (scope == "all" and effective[codigo] == "own"):
            effective[codigo] = scope
    return effective


async def get_user_permissions(
    user_id: UUID,
    tenant_id: UUID,
    session: AsyncSession,
) -> dict[str, str]:
    """Return all effective permissions for a user (code → scope).

    Delegates to ``_resolve_effective_permissions``.
    """
    return await _resolve_effective_permissions(user_id, tenant_id, session)


async def check_permission(
    user_id: UUID,
    tenant_id: UUID,
    permission_codigo: str,
    session: AsyncSession,
) -> PermissionCheck:
    """Check if a user has a specific permission.

    Resolves the full permission map via ``_resolve_effective_permissions``
    and looks up ``permission_codigo`` in the result.  This guarantees that
    ``check_permission`` and ``get_user_permissions`` can never diverge.

    Args:
        user_id: The user's UUID.
        tenant_id: The tenant's UUID.
        permission_codigo: The permission code to check
                           (e.g., ``"calificaciones:importar"``).
        session: An async SQLAlchemy session.

    Returns:
        A ``PermissionCheck`` with ``granted`` and ``scope``.
    """
    permissions = await _resolve_effective_permissions(user_id, tenant_id, session)
    scope = permissions.get(permission_codigo)
    if scope is None:
        return PermissionCheck(granted=False, scope=None)
    return PermissionCheck(granted=True, scope=scope)


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
