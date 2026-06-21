"""Closed catalog of audit action codes (RN-24).

Every action code used in AuditService.log() must appear in VALID_ACTION_CODES.
Adding a new code requires updating this file — making the catalog explicitly versioned.
"""

# Active in C-05
IMPERSONACION_INICIAR = "IMPERSONACION_INICIAR"
IMPERSONACION_FINALIZAR = "IMPERSONACION_FINALIZAR"

# C-07+
CALIFICACIONES_IMPORTAR = "CALIFICACIONES_IMPORTAR"
PADRON_CARGAR = "PADRON_CARGAR"
ASIGNACION_MODIFICAR = "ASIGNACION_MODIFICAR"
LIQUIDACION_CERRAR = "LIQUIDACION_CERRAR"

# C-12 — comunicaciones (RN-23, Q2 de la propuesta)
COMUNICACION_ENVIAR = "COMUNICACION_ENVIAR"
COMUNICACION_APROBAR = "COMUNICACION_APROBAR"

# C-14 — evaluaciones-y-coloquios
RESULTADO_REGISTRAR = "RESULTADO_REGISTRAR"

# C-15 — avisos-y-acknowledgment (VALID_ACTION_CODES: concern #3 / RN-24)
AVISO_CREAR = "AVISO_CREAR"
AVISO_ACK   = "AVISO_ACK"

# C-18 — liquidaciones-y-honorarios (RN-23, RN-24)
GRILLA_SALARIAL_OPERAR = "GRILLA_SALARIAL_OPERAR"  # alta/edición/baja de Base, Plus, MateriaGrupo
FACTURA_ABONAR         = "FACTURA_ABONAR"           # marcar Factura como Abonada

# C-20 — perfil-y-mensajeria-interna
PERFIL_ACTUALIZAR = "PERFIL_ACTUALIZAR"

VALID_ACTION_CODES: frozenset[str] = frozenset(
    {
        IMPERSONACION_INICIAR,
        IMPERSONACION_FINALIZAR,
        CALIFICACIONES_IMPORTAR,
        PADRON_CARGAR,
        COMUNICACION_ENVIAR,
        COMUNICACION_APROBAR,
        ASIGNACION_MODIFICAR,
        LIQUIDACION_CERRAR,
        RESULTADO_REGISTRAR,
        AVISO_CREAR,
        AVISO_ACK,
        GRILLA_SALARIAL_OPERAR,
        FACTURA_ABONAR,
        PERFIL_ACTUALIZAR,
    }
)
