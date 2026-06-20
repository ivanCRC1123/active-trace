"""UsuarioService — business logic for user ABM with PII encryption (C-07).

ValueError messages:
  "email ya existe"              → router maps to HTTP 409
  "usuario not found"            → router maps to HTTP 404
  "tiene asignaciones vigentes"  → router maps to HTTP 400
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import hmac_email
from app.core.security import hash_password
from app.models.user import User
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.usuarios import UsuarioCreate, UsuarioResponse, UsuarioUpdate


class UsuarioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: UUID) -> UsuarioRepository:
        return UsuarioRepository(self._session, tenant_id)

    @staticmethod
    def _to_response(user: User) -> UsuarioResponse:
        return UsuarioResponse(
            id=user.id,
            tenant_id=user.tenant_id,
            nombre=user.nombre,
            apellidos=user.apellidos,
            email=user.email_cifrado,
            dni=user.dni_cifrado,
            cuil=user.cuil_cifrado,
            cbu=user.cbu_cifrado,
            alias_cbu=user.alias_cbu_cifrado,
            banco=user.banco,
            regional=user.regional,
            legajo=user.legajo,
            legajo_profesional=user.legajo_profesional,
            facturador=user.facturador,
            estado="Activo" if user.is_active else "Inactivo",
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def create_usuario(self, *, tenant_id: UUID, data: UsuarioCreate) -> UsuarioResponse:
        repo = self._repo(tenant_id)
        if await repo.get_by_email_hash(str(data.email)) is not None:
            raise ValueError("email ya existe en este tenant")
        user = User(
            email_cifrado=str(data.email),
            email_hash=hmac_email(str(data.email)),
            password_hash=hash_password(data.password),
            nombre=data.nombre,
            apellidos=data.apellidos,
            dni_cifrado=data.dni,
            cuil_cifrado=data.cuil,
            cbu_cifrado=data.cbu,
            alias_cbu_cifrado=data.alias_cbu,
            banco=data.banco,
            regional=data.regional,
            legajo=data.legajo,
            legajo_profesional=data.legajo_profesional,
            facturador=data.facturador,
            is_active=True,
            is_2fa_enabled=False,
        )
        created = await repo.create(user)
        return self._to_response(created)

    async def list_usuarios(self, *, tenant_id: UUID) -> list[UsuarioResponse]:
        return [self._to_response(u) for u in await self._repo(tenant_id).list()]

    async def get_usuario(self, *, id: UUID, tenant_id: UUID) -> UsuarioResponse:
        user = await self._repo(tenant_id).get_by_id(id)
        if user is None:
            raise ValueError("usuario not found")
        return self._to_response(user)

    async def update_usuario(
        self, *, id: UUID, tenant_id: UUID, data: UsuarioUpdate
    ) -> UsuarioResponse:
        update_data = data.model_dump(exclude_unset=True)
        if "estado" in update_data:
            update_data["is_active"] = update_data.pop("estado") == "Activo"
        pii_map = [
            ("dni", "dni_cifrado"),
            ("cuil", "cuil_cifrado"),
            ("cbu", "cbu_cifrado"),
            ("alias_cbu", "alias_cbu_cifrado"),
        ]
        for src, dst in pii_map:
            if src in update_data:
                update_data[dst] = update_data.pop(src)
        updated = await self._repo(tenant_id).update(id, update_data)
        if updated is None:
            raise ValueError("usuario not found")
        return self._to_response(updated)

    async def delete_usuario(self, *, id: UUID, tenant_id: UUID) -> None:
        repo = self._repo(tenant_id)
        if await repo.get_by_id(id) is None:
            raise ValueError("usuario not found")
        if await repo.has_asignaciones_vigentes(id):
            raise ValueError("tiene asignaciones vigentes — desvinculá primero")
        await repo.soft_delete(id)
