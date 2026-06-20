#!/usr/bin/env python3
"""Seed the initial ADMIN user for the "TUPAD" tenant.

Usage:
    python scripts/seed_admin.py

Environment variables (all optional):
    SEED_ADMIN_EMAIL     — Admin email (default: admin@tupad.edu.ar)
    SEED_ADMIN_PASSWORD  — Admin password (default: Admin123!)
    SEED_TENANT_CODE     — Target tenant code (default: tupad)

The script is idempotent: if the user already exists (by email), it
skips creation and logs a message. The default password is suitable
for local development only — in production, always set
``SEED_ADMIN_PASSWORD``.
"""

import logging
import os

from app.core.config import settings
from app.core.database import Base, engine, init_engine
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("seed_admin")

# ── Config (from env with dev defaults) ──────────────────────────────────

ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@tupad.edu.ar")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "Admin123!")
TENANT_CODE = os.getenv("SEED_TENANT_CODE", "tupad")
ADMIN_NOMBRE = os.getenv("SEED_ADMIN_NOMBRE", "Admin")
ADMIN_APELLIDO = os.getenv("SEED_ADMIN_APELLIDO", "Sistema")


async def seed() -> None:
    """Run the seed — create ADMIN user for the target tenant."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    init_engine()
    if engine is None:
        raise RuntimeError("Engine not initialised")

    async with AsyncSession(engine) as session:
        # Find tenant
        stmt = select(Tenant).where(
            Tenant.codigo == TENANT_CODE,
            Tenant.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

        if tenant is None:
            logger.error("Tenant with code '%s' not found. Seed the tenant first.", TENANT_CODE)
            return

        logger.info("Found tenant: %s (%s)", tenant.codigo, tenant.nombre)

        # Check if admin already exists
        from app.repositories.user_repository import UserRepository
        repo = UserRepository(session, tenant.id)
        existing = await repo.get_by_email_hash(ADMIN_EMAIL)

        if existing is not None:
            logger.info("Admin user already exists — skipping.")
            return

        # Create admin user (email cifrado + blind index)
        from app.core.encryption import encrypt, hmac_email  # noqa: PLC0415
        admin = User(
            email_cifrado=encrypt(ADMIN_EMAIL),
            email_hash=hmac_email(ADMIN_EMAIL),
            password_hash=hash_password(ADMIN_PASSWORD),
            nombre=ADMIN_NOMBRE,
            apellidos=ADMIN_APELLIDO,
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tenant.id,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        logger.info("Admin user created: id=%s", admin.id)
        logger.info("Password: *** (set via SEED_ADMIN_PASSWORD env var)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(seed())
