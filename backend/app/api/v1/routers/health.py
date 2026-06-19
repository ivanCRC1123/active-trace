"""Health-check endpoint.

Provides ``GET /health`` which reports application liveness and
database readiness. The database check gracefully degrades — if the
connection fails the endpoint still returns ``200`` with
``database: "down"``.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Report application and database health.

    Returns:
        A JSON dict with ``status`` (always ``"ok"``) and ``database``
        (``"up"`` or ``"down"``). A failed database check does **not**
        cause a ``500`` — the endpoint degrades gracefully.
    """
    db_status = "up"
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() != 1:
            db_status = "down"
    except Exception:  # noqa: BLE001
        logger.warning("Health-check database ping failed", exc_info=True)
        db_status = "down"

    return {"status": "ok", "database": db_status}
