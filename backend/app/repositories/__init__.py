"""Repositories for activia-trace domain models."""

from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.base import BaseRepository
from app.repositories.carrera_repository import CarreraRepository
from app.repositories.cohorte_repository import CohorteRepository
from app.repositories.materia_repository import MateriaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.repositories.user_repository import UserRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.recovery_token_repository import RecoveryTokenRepository
from app.repositories.rol_repository import RolRepository
from app.repositories.permiso_repository import PermisoRepository
from app.repositories.rol_permiso_repository import RolPermisoRepository
from app.repositories.user_rol_repository import UserRolRepository

__all__ = [
    "AsignacionRepository",
    "AuditLogRepository",
    "BaseRepository",
    "CarreraRepository",
    "CohorteRepository",
    "MateriaRepository",
    "UsuarioRepository",
    "UserRepository",
    "RefreshTokenRepository",
    "RecoveryTokenRepository",
    "RolRepository",
    "PermisoRepository",
    "RolPermisoRepository",
    "UserRolRepository",
]
