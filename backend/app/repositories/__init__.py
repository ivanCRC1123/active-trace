"""Repositories for activia-trace domain models."""

from app.repositories.base import BaseRepository
from app.repositories.rol_repository import RolRepository
from app.repositories.permiso_repository import PermisoRepository
from app.repositories.rol_permiso_repository import RolPermisoRepository
from app.repositories.user_rol_repository import UserRolRepository

__all__ = [
    "BaseRepository",
    "RolRepository",
    "PermisoRepository",
    "RolPermisoRepository",
    "UserRolRepository",
]