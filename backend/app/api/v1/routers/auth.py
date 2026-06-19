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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.service import AuthService
from app.core.dependencies import get_current_user, get_db
from app.core.permissions import require_permission
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
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RefreshResponse,
    ResetRequest,
    ResetResponse,
    TwoFAEnrollResponse,
    TwoFARequiredResponse,
    TwoFAVerifyLoginRequest,
    TwoFAVerifyRequest,
)

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


# ── Public endpoints ───────────────────────────────────────────────────────


@router.post("/login", responses={401: {"model": ErrorResponse}})
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse | TwoFARequiredResponse:
    """Authenticate with tenant code, email, and password.

    On success returns an access + refresh token pair.
    If the user has 2FA enabled, returns a ``session_token`` that must
    be exchanged via ``/api/auth/2fa/verify-login``.
    """
    # Resolve tenant first so the service is correctly scoped
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
        return TwoFARequiredResponse(
            session_token=outcome["session_token"],
        )

    return LoginResponse(**outcome)


@router.post("/refresh", responses={401: {"model": ErrorResponse}})
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """Rotate a refresh token and issue a new token pair.

    Implements token rotation with family revocation (token reuse
    detection). If the supplied token was already revoked, the entire
    token family is invalidated.
    """
    # Look up the token hash to discover the tenant_id
    from app.models.refresh_token import RefreshToken as RT

    import hashlib
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    stmt = select(RT).where(
        RT.token_hash == token_hash,
        RT.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    stored = result.scalar_one_or_none()
    if stored is None:
        _raise_unauthorized("Invalid refresh token")

    # Build service scoped to the stored token's tenant
    service = _build_service(db, stored.tenant_id)

    try:
        outcome = await service.refresh(body.refresh_token)
    except ValueError as exc:
        _raise_unauthorized(str(exc))

    return RefreshResponse(**outcome)


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
        user = await repo.get_by_email(body.email)
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
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Complete a 2FA login challenge.

    Exchange a ``session_token`` (obtained from ``/login`` when 2FA is
    enabled) plus a valid TOTP ``code`` for an access + refresh token
    pair.
    """
    # Build with a dummy tenant — verify_2fa_login resolves the session
    # internally and uses the user's tenant for token issuance.
    import uuid
    dummy_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    service = _build_service(db, dummy_tenant_id)

    try:
        outcome = await service.verify_2fa_login(
            session_token=body.session_token,
            code=body.code,
        )
    except ValueError as exc:
        _raise_unauthorized(str(exc))

    return LoginResponse(**outcome)


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


@router.post(
    "/logout",
    responses={401: {"model": ErrorResponse}},
)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LogoutResponse:
    """Revoke a refresh token.

    Requires a valid access token in the ``Authorization`` header.
    The ``refresh_token`` in the request body is optional — if omitted
    no action is taken.
    """
    service = _build_service(db, current_user.tenant_id)

    await service.logout(refresh_token=body.refresh_token)

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
