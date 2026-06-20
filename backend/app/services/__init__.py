"""Services for activia-trace."""

from app.services.asignacion_service import AsignacionService
from app.services.avisos_service import AvisosService
from app.services.audit_service import AuditService
from app.services.coloquios_service import ColoquiosService
from app.services.estructura_academica_service import EstructuraAcademicaService
from app.services.padron_service import PadronService
from app.services.programas_service import ProgramasService
from app.services.usuario_service import UsuarioService

__all__ = [
    "AsignacionService",
    "AuditService",
    "AvisosService",
    "ColoquiosService",
    "EstructuraAcademicaService",
    "PadronService",
    "ProgramasService",
    "UsuarioService",
]
