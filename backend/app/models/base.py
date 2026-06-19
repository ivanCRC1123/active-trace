"""Base ORM mixins for all domain entities.

Provides composable mixins:

- ``TimeStampedMixin``: ``id`` (UUID PK), ``created_at``, ``updated_at``
- ``SoftDeleteMixin``: ``deleted_at`` (nullable)
- ``TenantScopedMixin``: ``tenant_id`` (FK → ``tenant.id``)
- ``BaseEntityMixin``: combines all three.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class TimeStampedMixin:
    """Adds ``id`` (UUID PK), ``created_at`` and ``updated_at`` columns."""

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds a nullable ``deleted_at`` column for soft deletion."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        default=None,
    )


class TenantScopedMixin:
    """Adds a ``tenant_id`` FK column referencing ``tenant.id``."""

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )


class BaseEntityMixin(TimeStampedMixin, SoftDeleteMixin, TenantScopedMixin):
    """Convenience mixin that combines all three base mixins.

    Most domain models should inherit this mixin to get:
    - UUID primary key (auto-generated)
    - ``created_at`` / ``updated_at`` timestamps
    - ``deleted_at`` (soft delete)
    - ``tenant_id`` (multi-tenant isolation)
    """
