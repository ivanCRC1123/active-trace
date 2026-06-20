"""Generic repository with tenant-scoped queries.

``BaseRepository[T]`` implements CRUD operations that **always** filter
by ``tenant_id`` (ADR-002 row-level isolation). The tenant id is injected
at construction time so it cannot be forgotten per-call.

No ``hard_delete`` method is exposed — only ``soft_delete`` which sets
``deleted_at``.
"""

from typing import Generic, Sequence, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.base import BaseEntityMixin

ModelT = TypeVar("ModelT", bound=BaseEntityMixin)


class BaseRepository(Generic[ModelT]):
    """Generic tenant-scoped repository.

    All queries automatically include ``WHERE tenant_id = :tenant_id``.
    """

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._model_class: type[ModelT] | None = None

    @property
    def model_class(self) -> type[ModelT]:
        if self._model_class is None:
            raise NotImplementedError(
                "Subclasses must set _model_class or override model_class"
            )
        return self._model_class

    async def list(self) -> Sequence[ModelT]:
        """Return active (non-deleted) records scoped to the tenant."""
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, id: str) -> ModelT | None:
        """Return a non-deleted record by id if it belongs to the tenant."""
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.id == id,
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: ModelT | dict) -> ModelT:
        """Create a new record scoped to the tenant.

        Accepts either a model instance or a dict of column values.
        The ``tenant_id`` is always set from the repository's scope.
        """
        if isinstance(data, dict):
            model = self.model_class(**data, tenant_id=self._tenant_id)
        else:
            model = data
            model.tenant_id = self._tenant_id
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(self, id: str, data: dict) -> ModelT | None:
        """Update a record by id if it belongs to the tenant."""
        model = await self.get_by_id(id)
        if model is None:
            return None
        for key, value in data.items():
            setattr(model, key, value)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def soft_delete(self, id: str) -> bool:
        """Soft-delete a record by setting ``deleted_at``.

        Returns ``True`` if the record was found and deleted, ``False``
        if the record does not exist (or does not belong to the tenant).
        """
        model = await self.get_by_id(id)
        if model is None:
            return False
        model.deleted_at = func.now()
        await self._session.flush()
        return True

    async def list_with_deleted(self) -> Sequence[ModelT]:
        """Return all records scoped to the tenant, including soft-deleted.

        The tenant filter is **never** omitted — even for audit queries.
        """
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
