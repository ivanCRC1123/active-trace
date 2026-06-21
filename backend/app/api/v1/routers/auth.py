"""Authentication and token management endpoints.

Provides:
- ``POST /api/auth/login`` — authenticate with email + password
- ``POST /api/auth/refresh`` — rotate refresh token
- ``POST /api/auth/logout`` — revoke refresh token (protected)
- ``POST /api/auth/forgot`` — request password recovery token
- ``POST /api/auth/reset`` — reset password with recovery token
- ``POST /api/auth/2fa/enroll`` — generate TOTP secret (protected)
- ``POST /api/auth/2fa/verify`` — verify TOTP and enable 2FA (protected)
- ``POST /api/auth/2fa/verify-login`` — complete 2FA login challenge
"""

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import IMPERSONACION_FINALIZAR, IMPERSONACION_INICIAR
from app.core.auth.service import AuthService
from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.permissions import get_user_permissions, require_permission
from app.core.security import create_access_token
from app.models.tenant import Tenant
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.recovery_token_repository import RecoveryTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    CurrentUser,
    ErrorResponse,
    ForgotRequest,
    ForgotResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MePermissionsResponse,
    RefreshResponse,
    ResetRequest,
    ResetResponse,
    TwoFAEnrollResponse,
    TwoFARequiredResponse,
    TwoFAVerifyLoginRequest,
    TwoFAVerifyRequest,
)
from app.schemas.auditoria import ImpersonateRequest, ImpersonateResponse
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_service(db: AsyncSession, tenant_id) -> AuthService:
    """Build an AuthService with default repository wiring.

    The tenant_id must already be resolved before calling this helper.
    """
    return AuthService(
        session=db,
        tenant_id=tenant_id,
        user_repo=UserRepository(db, tenant_id),
        refresh_repo=RefreshTokenRepository(db, tenant_id),
        recovery_repo=RecoveryTokenRepository(db, tenant_id),
    )


def _raise_unauthorized(detail: str = "Invalid credentials") -> None:
    """Raise a 401 with a consistent error body."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Write the refresh token as an httpOnly cookie.

    ``Secure`` is controlled by ``settings.COOKIE_SECURE``:
    - ``False`` in local dev (http://localhost — Secure would silently drop it).
    - ``True`` in production (HTTPS only).
    ``SameSite=Strict`` prevents the cookie from being sent on cross-site
    requests, mitigating CSRF without needing an additional CSRF token.
    ``Path`` is scoped to ``/api/auth`` so the cookie is never sent to
    unrelated endpoints.
    """
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        path=_REFRESH_COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Expire the refresh token cookie (max_age=0).

    Attributes must match the original ``set_cookie`` call so the browser
    identifies the correct cookie to expire.
    """
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.COOKIE_SECURE,
    )


# ── Public endpoints ───────────────────────────────────────────────────────


@router.post("/login", responses={401: {"model": ErrorResponse}})
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse | TwoFARequiredResponse:
    """Authenticate with tenant code, email, and password.

    On success returns an access token in the JSON body and sets the
    refresh token as an httpOnly ``SameSite=Strict`` cookie.
    If the user has 2FA enabled, returns a ``session_token`` instead
    (no tokens issued yet — exchange via ``/api/auth/2fa/verify-login``).
    """
    stmt = select(Tenant).where(
        Tenant.codigo == body.tenant_code,
        Tenant.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        _raise_unauthorized()

    service = _build_service(db, tenant.id)

    try:
        outcome = await service.login(
            tenant_code=body.tenant_code,
            email=body.email,
            password=body.password,
        )
    except ValueError as exc:
        _raise_unauthorized(str(exc))

    if "requires_2fa" in outcome:
        return TwoFARequiredResponse(session_token=outcome["session_token"])

    _set_refresh_cookie(response, outcome["refresh_token"])
    return LoginResponse(
        access_token=outcome["access_token"],
        token_type=outcome["token_type"],
        expires_in=outcome["expires_in"],
    )


@router.post("/refresh", responses={401: {"model": ErrorResponse}})
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """Rotate a refresh token and issue a new access token.

    Reads the refresh token from the ``refresh_token`` httpOnly cookie
    (set by ``/login`` or a prior ``/refresh`` call).  On success, the
    old cookie is replaced with a new one carrying the rotated token.
    Implements token rotation with family revocation: if the presented
    token was already revoked, the entire token family is invalidated.
    """
    if not refresh_token:
        _raise_unauthorized("Refresh token missing")

    import hashlib  # noqa: PLC0415

    from app.models.refresh_token import RefreshToken as RT  # noqa: PLC0415

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    stmt = select(RT).where(
        RT.token_hash == token_hash,
        RT.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    stored = result.scalar_one_or_none()
    if stored is None:
        _raise_unauthorized("Invalid refresh token")

    service = _build_service(db, stored.tenant_id)

    try:
        outcome = await service.refresh(refresh_token)
    except ValueError as exc:
        _raise_unauthorized(str(exc))

    _set_refresh_cookie(response, outcome["refresh_token"])
    return RefreshResponse(
        access_token=outcome["access_token"],
        token_type=outcome["token_type"],
        expires_in=outcome["expires_in"],
    )


@router.post("/forgot", responses={200: {"model": ForgotResponse}})
async def forgot_password(
    body: ForgotRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotResponse:
    """Request a password recovery token.

    The token is returned in the response body (for MVP — in production
    it would be sent via email). If the email does not exist, the
    endpoint returns 200 with an empty ``recovery_token`` (no user
    existence leak).
    """
    # Iterate over active tenants to find the user by email.
    # This is O(n_tenants) but acceptable for MVP (< 100 tenants).
    # A cross-tenant email lookup can be added later if needed.
    stmt = select(Tenant).where(Tenant.deleted_at.is_(None))
    result = await db.execute(stmt)
    tenants = result.scalars().all()

    raw_token: str | None = None
    for tenant in tenants:
        repo = UserRepository(db, tenant.id)
        user = await repo.get_by_email_hash(body.email)
        if user is not None:
            service = _build_service(db, tenant.id)
            raw_token = await service.forgot_password(
                tenant_code=tenant.codigo,
                email=body.email,
            )
            break

    return ForgotResponse(
        detail="If the email exists, a recovery token has been generated.",
        recovery_token=raw_token,  # None if email unknown
    )


@router.post("/reset", responses={401: {"model": ErrorResponse}})
async def reset_password(
    body: ResetRequest,
    db: AsyncSession = Depends(get_db),
) -> ResetResponse:
    """Reset password using a recovery token.

    The token is validated (not expired, not used), the password is
    updated, and the token is marked as used.
    """
    # Build service with dummy tenant — reset uses unscoped recovery
    # repo methods.
    import uuid
    dummy_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    service = _build_service(db, dummy_tenant_id)

    try:
        await service.reset_password(
            token=body.token,
            new_password=body.new_password,
        )
    except ValueError as exc:
        _raise_unauthorized(str(exc))

    return ResetResponse(detail="Password has been reset successfully.")


@router.post("/2fa/verify-login", responses={401: {"model": ErrorResponse}})
async def verify_2fa_login(
    body: TwoFAVerifyLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Complete a 2FA login challenge.

    Exchange a ``session_token`` (obtained from ``/login`` when 2FA is
    enabled) plus a valid TOTP ``code`` for an access token.  The refresh
    token is set as an httpOnly cookie — same contract as ``/login``.
    """
    import uuid  # noqa: PLC0415

    dummy_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    service = _build_service(db, dummy_tenant_id)

    try:
        outcome = await service.verify_2fa_login(
            session_token=body.session_token,
            code=body.code,
        )
    except ValueError as exc:
        _raise_unauthorized(str(exc))

    _set_refresh_cookie(response, outcome["refresh_token"])
    return LoginResponse(
        access_token=outcome["access_token"],
        token_type=outcome["token_type"],
        expires_in=outcome["expires_in"],
    )


# ── Protected endpoints (require valid JWT) ────────────────────────────────


@router.get(
    "/me",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_me(
    _: tuple[CurrentUser, str | None] = Depends(
        require_permission("comunicacion:confirmar_aviso"),
    ),
) -> CurrentUser:
    """Return the current authenticated user's profile.

    Requires ``comunicacion:confirmar_aviso`` permission (granted to all 7 roles).
    Demonstrates the ``require_permission`` guard — all authenticated
    users with any role can access their own profile.
    """
    current_user, _scope = _
    return current_user


@router.get(
    "/me/permissions",
    responses={401: {"model": ErrorResponse}},
)
async def get_me_permissions(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MePermissionsResponse:
    """Return effective permissions for the authenticated user.

    Resolves the union of all active role assignments via
    ``get_user_permissions``.  The frontend uses this to drive route
    guards and menu visibility without duplicating the RBAC matrix.
    """
    permissions = await get_user_permissions(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        session=db,
    )
    return MePermissionsResponse(permissions=permissions)


@router.post(
    "/logout",
    responses={401: {"model": ErrorResponse}},
)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LogoutResponse:
    """Revoke the current refresh token and clear the cookie.

    Reads the refresh token from the ``refresh_token`` httpOnly cookie.
    If the cookie is absent the server-side revocation is skipped, but
    the cookie is still cleared in the response.  This keeps logout
    idempotent (calling it twice is safe).
    """
    service = _build_service(db, current_user.tenant_id)
    await service.logout(refresh_token=refresh_token)
    _clear_refresh_cookie(response)
    return LogoutResponse(detail="Logged out successfully.")


@router.post(
    "/2fa/enroll",
    response_model=TwoFAEnrollResponse,
    responses={401: {"model": ErrorResponse}},
)
async def enroll_2fa(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TwoFAEnrollResponse:
    """Generate a TOTP secret and provisioning URI.

    Does **not** enable 2FA yet — call ``/api/auth/2fa/verify`` with a
    valid TOTP code to activate it.
    """
    service = _build_service(db, current_user.tenant_id)

    try:
        result = await service.enroll_2fa(user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return TwoFAEnrollResponse(secret=result["secret"], uri=result["uri"])


@router.post(
    "/2fa/verify",
    responses={
        200: {"description": "2FA enabled successfully"},
        401: {"model": ErrorResponse},
    },
)
async def verify_2fa(
    body: TwoFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Verify a TOTP code and enable 2FA for the current user.

    Requires a valid access token and a prior call to
    ``/api/auth/2fa/enroll``.
    """
    service = _build_service(db, current_user.tenant_id)

    try:
        await service.enable_2fa(
            user_id=current_user.user_id,
            code=body.code,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return {"detail": "2FA has been enabled successfully."}


# ── Impersonation endpoints ────────────────────────────────────────────────


@router.post(
    "/impersonate",
    responses={
        200: {"model": ImpersonateResponse},
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def start_impersonate(
    body: ImpersonateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(require_permission("impersonacion:usar")),
) -> ImpersonateResponse:
    """Begin an impersonation session as another user in the same tenant.

    Issues a new access token carrying an ``impersonado_id`` claim.
    The real actor's identity is preserved; all subsequent audit events
    will record the real actor_id alongside the impersonated user.
    """
    current_user, _ = _

    user_repo = UserRepository(db, current_user.tenant_id)
    target = await user_repo.get_by_id(body.target_user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")
    if not target.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user is inactive")

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Build a ctx that captures "actor=admin, impersonado=target" for the INICIAR row.
    # current_user.impersonado_id is None here (the impersonation hasn't started yet).
    from app.schemas.auth import CurrentUser as _CU  # noqa: PLC0415
    ctx_for_log = _CU(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        roles=current_user.roles,
        impersonado_id=body.target_user_id,
    )
    audit = AuditService(db)
    await audit.log(
        current_user=ctx_for_log,
        accion=IMPERSONACION_INICIAR,
        detalle={"target_user_id": str(body.target_user_id)},
        filas_afectadas=1,
        ip=ip,
        user_agent=user_agent,
    )

    token = create_access_token(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        roles=current_user.roles,
        impersonado_id=body.target_user_id,
    )
    return ImpersonateResponse(access_token=token, impersonado_id=body.target_user_id)


@router.post(
    "/impersonate/end",
    responses={
        200: {"description": "Impersonation ended"},
        400: {"model": ErrorResponse},
    },
)
async def end_impersonate(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """End the current impersonation session and issue a clean access token.

    Logs IMPERSONACION_FINALIZAR before issuing the clean token.
    Returns 400 if the caller is not currently impersonating.
    """
    if current_user.impersonado_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active impersonation session",
        )

    impersonado_id = current_user.impersonado_id
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    audit = AuditService(db)
    await audit.log(
        current_user=current_user,
        accion=IMPERSONACION_FINALIZAR,
        detalle={"target_user_id": str(impersonado_id)},
        filas_afectadas=1,
        ip=ip,
        user_agent=user_agent,
    )

    clean_token = create_access_token(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        roles=current_user.roles,
        impersonado_id=None,
    )
    return {"access_token": clean_token, "token_type": "bearer"}
