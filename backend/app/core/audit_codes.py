"""Closed catalog of audit action codes (RN-24).

Every action code used in AuditService.log() must appear in VALID_ACTION_CODES.
Adding a new code requires updating this file — making the catalog explicitly versioned.
"""

# Active in C-05
IMPERSONACION_INICIAR = "IMPERSONACION_INICIAR"
IMPERSONACION_FINALIZAR = "IMPERSONACION_FINALIZAR"

# Stubs — defined here, called by future changes (C-07+)
CALIFICACIONES_IMPORTAR = "CALIFICACIONES_IMPORTAR"
PADRON_CARGAR = "PADRON_CARGAR"
COMUNICACION_ENVIAR = "COMUNICACION_ENVIAR"
ASIGNACION_MODIFICAR = "ASIGNACION_MODIFICAR"
LIQUIDACION_CERRAR = "LIQUIDACION_CERRAR"

VALID_ACTION_CODES: frozenset[str] = frozenset(
    {
        IMPERSONACION_INICIAR,
        IMPERSONACION_FINALIZAR,
        CALIFICACIONES_IMPORTAR,
        PADRON_CARGAR,
        COMUNICACION_ENVIAR,
        ASIGNACION_MODIFICAR,
        LIQUIDACION_CERRAR,
    }
)
