#!/usr/bin/env python3
"""Seed the initial tenant (TUPAD) for development.

Usage:
    python scripts/seed_tenant.py

Environment variables (all optional):
    SEED_TENANT_CODE    — Tenant code (default: tupad)
    SEED_TENANT_NOMBRE  — Tenant name (default: TUPAD)
"""

import logging
import os

from app.core.database import AsyncSession, engine, init_engine
from app.models.tenant import Tenant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("seed_tenant")

TENANT_CODE = os.getenv("SEED_TENANT_CODE", "tupad")
TENANT_NOMBRE = os.getenv("SEED_TENANT_NOMBRE", "TUPAD")


async def seed() -> None:
    from sqlalchemy import select

    init_engine()
    if engine is None:
        raise RuntimeError("Engine not initialised")

    async with AsyncSession(engine) as session:
        stmt = select(Tenant).where(
            Tenant.codigo == TENANT_CODE,
            Tenant.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            logger.info("Tenant '%s' already exists — skipping.", TENANT_CODE)
            return

        tenant = Tenant(codigo=TENANT_CODE, nombre=TENANT_NOMBRE)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        logger.info("Tenant created: code=%s name=%s id=%s", tenant.codigo, tenant.nombre, tenant.id)


if __name__ == "__main__":
    import asyncio

    asyncio.run(seed())
