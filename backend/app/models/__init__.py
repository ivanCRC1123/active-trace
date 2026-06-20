"""Domain models for activia-trace."""

from app.models.comunicacion import Comunicacion, EstadoComunicacion, TRANSICIONES_VALIDAS, validar_transicion
from app.models.asignacion import Asignacion
from app.models.calificacion import Calificacion, OrigenCalificacion
from app.models.fecha_academica import FechaAcademica
from app.models.finalizacion_actividad import FinalizacionActividad
from app.models.entrada_padron import EntradaPadron
from app.models.version_padron import VersionPadron
from app.models.audit_log import AuditLog
from app.models.base import BaseEntityMixin, EncryptedString, EstadoBasico, SoftDeleteMixin, TenantScopedMixin, TimeStampedMixin, TipoEvaluacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.programa_materia import ProgramaMateria
from app.models.recovery_token import RecoveryToken
from app.models.refresh_token import RefreshToken
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.umbral_materia import UmbralMateria
from app.models.user import User
from app.models.user_rol import UserRol

__all__ = [
    "Comunicacion",
    "EstadoComunicacion",
    "TRANSICIONES_VALIDAS",
    "validar_transicion",
    "Asignacion",
    "AuditLog",
    "Calificacion",
    "FechaAcademica",
    "FinalizacionActividad",
    "OrigenCalificacion",
    "EntradaPadron",
    "VersionPadron",
    "BaseEntityMixin",
    "EncryptedString",
    "Carrera",
    "Cohorte",
    "EstadoBasico",
    "Materia",
    "ProgramaMateria",
    "SoftDeleteMixin",
    "TenantScopedMixin",
    "TimeStampedMixin",
    "TipoEvaluacion",
    "Tenant",
    "UmbralMateria",
    "User",
    "RefreshToken",
    "RecoveryToken",
    "Rol",
    "Permiso",
    "RolPermiso",
    "UserRol",
]
