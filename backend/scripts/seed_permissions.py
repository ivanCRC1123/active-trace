#!/usr/bin/env python3
"""Seed the RBAC roles, permissions, and Rol↔Permiso matrix.

Creates 7 roles, all 20 permissions from the §3.3 matrix, the full
Rol↔Permiso entries with scope markers, and assigns ADMIN role to
the seed admin user.

Usage:
    python scripts/seed_permissions.py

Environment variables (all optional):
    SEED_TENANT_CODE     — Target tenant code (default: tupad)
    SEED_ADMIN_EMAIL     — Admin user email (default: admin@tupad.edu.ar)

The script is fully idempotent: it checks existence by
(tenant_id + nombre/codigo) before inserting.
"""

import logging
import os

from app.core.database import Base, engine, init_engine
from app.models.tenant import Tenant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("seed_permissions")

TENANT_CODE = os.getenv("SEED_TENANT_CODE", "tupad")
ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@tupad.edu.ar")

# ── Permission matrix: role → { permission_code → scope } ──────────
# Source of truth: openspec/changes/c-04-rbac-permisos-finos/specs/role-catalog/spec.md
# and knowledge-base/03_actores_y_roles.md §3.3
# ✅ → scope='all', (propio) → scope='own', — → not included

PERMISSION_MATRIX: dict[str, dict[str, str]] = {
    "ALUMNO": {
        "estado_academico:ver_propio": "all",
        "evaluacion:reservar": "all",
        "comunicacion:confirmar_aviso": "all",
    },
    "TUTOR": {
        "comunicacion:confirmar_aviso": "all",
        "atrasados:ver": "all",
        "entregas:detectar_sin_corregir": "all",
        "encuentros:gestionar": "all",
        "guardias:registrar": "own",
    },
    "PROFESOR": {
        "comunicacion:confirmar_aviso": "all",
        "calificaciones:importar": "own",
        "atrasados:ver": "own",
        "entregas:detectar_sin_corregir": "own",
        "comunicacion:enviar": "own",
        "encuentros:gestionar": "own",
        "guardias:registrar": "own",
        "tareas_internas:gestionar": "own",
    },
    "COORDINADOR": {
        "comunicacion:confirmar_aviso": "all",
        "calificaciones:importar": "all",
        "atrasados:ver": "all",
        "entregas:detectar_sin_corregir": "all",
        "comunicacion:enviar": "all",
        "comunicacion:aprobar": "all",
        "encuentros:gestionar": "all",
        "guardias:registrar": "all",
        "tareas_internas:gestionar": "all",
        "avisos:publicar": "all",
        "equipos:asignar": "all",
        "auditoria:ver": "own",
    },
    # ADMIN has scope='all' for all permissions except those exclusive to FINANZAS
    # (grilla_salarial:operar, liquidaciones:calcular_cerrar, facturas:gestionar)
    "ADMIN": {
        "estado_academico:ver_propio": "all",
        "evaluacion:reservar": "all",
        "comunicacion:confirmar_aviso": "all",
        "calificaciones:importar": "all",
        "atrasados:ver": "all",
        "entregas:detectar_sin_corregir": "all",
        "comunicacion:enviar": "all",
        "comunicacion:aprobar": "all",
        "encuentros:gestionar": "all",
        "guardias:registrar": "all",
        "tareas_internas:gestionar": "all",
        "avisos:publicar": "all",
        "equipos:asignar": "all",
        "estructura_academica:gestionar": "all",
        "usuarios:gestionar": "all",
        "auditoria:ver": "all",
        "tenant:configurar": "all",
        "impersonacion:usar": "all",
    },
    "NEXO": {
        "comunicacion:confirmar_aviso": "all",
    },
    "FINANZAS": {
        "comunicacion:confirmar_aviso": "all",
        "auditoria:ver": "all",
        "grilla_salarial:operar": "all",
        "liquidaciones:calcular_cerrar": "all",
        "facturas:gestionar": "all",
    },
}

# ── All 20 unique permission definitions with their modulo ──────────
# Exact codes from role-catalog/spec.md §"All permissions from the matrix are seeded"

PERMISOS: list[dict[str, str]] = [
    {"codigo": "estado_academico:ver_propio",    "modulo": "estado_academico",  "descripcion": "Ver estado académico propio"},
    {"codigo": "evaluacion:reservar",            "modulo": "evaluacion",        "descripcion": "Reservar instancia de evaluación"},
    {"codigo": "comunicacion:confirmar_aviso",   "modulo": "comunicacion",      "descripcion": "Confirmar aviso (acknowledgment)"},
    {"codigo": "calificaciones:importar",        "modulo": "calificaciones",    "descripcion": "Importar calificaciones"},
    {"codigo": "atrasados:ver",                  "modulo": "atrasados",         "descripcion": "Ver alumnos atrasados"},
    {"codigo": "entregas:detectar_sin_corregir", "modulo": "entregas",          "descripcion": "Detectar entregas sin corregir"},
    {"codigo": "comunicacion:enviar",            "modulo": "comunicacion",      "descripcion": "Enviar comunicaciones a alumnos"},
    {"codigo": "comunicacion:aprobar",           "modulo": "comunicacion",      "descripcion": "Aprobar comunicaciones masivas"},
    {"codigo": "encuentros:gestionar",           "modulo": "encuentros",        "descripcion": "Gestionar encuentros"},
    {"codigo": "guardias:registrar",             "modulo": "guardias",          "descripcion": "Registrar guardias"},
    {"codigo": "tareas_internas:gestionar",      "modulo": "tareas_internas",   "descripcion": "Gestionar tareas internas"},
    {"codigo": "avisos:publicar",                "modulo": "avisos",            "descripcion": "Publicar avisos"},
    {"codigo": "equipos:asignar",                "modulo": "equipos",           "descripcion": "Gestionar equipos docentes"},
    {"codigo": "estructura_academica:gestionar", "modulo": "estructura_academica", "descripcion": "Gestionar estructura académica"},
    {"codigo": "usuarios:gestionar",             "modulo": "usuarios",          "descripcion": "Gestionar usuarios del tenant"},
    {"codigo": "auditoria:ver",                  "modulo": "auditoria",         "descripcion": "Ver auditoría"},
    {"codigo": "grilla_salarial:operar",         "modulo": "grilla_salarial",   "descripcion": "Operar grilla salarial"},
    {"codigo": "liquidaciones:calcular_cerrar",  "modulo": "liquidaciones",     "descripcion": "Calcular / cerrar liquidaciones"},
    {"codigo": "facturas:gestionar",             "modulo": "facturas",          "descripcion": "Gestionar facturas"},
    {"codigo": "tenant:configurar",              "modulo": "tenant",            "descripcion": "Configurar el tenant"},
    # Added in C-05: required by RN-41 and protect POST /auth/impersonate
    {"codigo": "impersonacion:usar",             "modulo": "impersonacion",     "descripcion": "Impersonar a otro usuario del tenant"},
]


async def seed() -> None:
    """Run the seed — create roles, permissions, matrix, and admin assignment."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.permiso import Permiso
    from app.models.rol import Rol
    from app.models.rol_permiso import RolPermiso
    from app.models.user_rol import UserRol

    init_engine()
    if engine is None:
        raise RuntimeError("Engine not initialised")

    async with AsyncSession(engine) as session:
        # ── Find tenant ──────────────────────────────────────────────
        stmt = select(Tenant).where(
            Tenant.codigo == TENANT_CODE,
            Tenant.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

        if tenant is None:
            logger.error("Tenant with code '%s' not found. Run seed_admin.py first.", TENANT_CODE)
            return

        logger.info("Found tenant: %s (%s)", tenant.codigo, tenant.nombre)
        tid = tenant.id

        # ── Create roles (idempotent) ────────────────────────────────
        role_names = list(PERMISSION_MATRIX.keys())
        created_roles: dict[str, Rol] = {}

        for nombre in role_names:
            stmt = select(Rol).where(
                Rol.tenant_id == tid,
                Rol.nombre == nombre,
                Rol.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("Role '%s' already exists — skipping.", nombre)
                created_roles[nombre] = existing
            else:
                rol = Rol(
                    tenant_id=tid,
                    nombre=nombre,
                    descripcion=f"Rol {nombre}",
                )
                session.add(rol)
                await session.flush()
                await session.refresh(rol)
                created_roles[nombre] = rol
                logger.info("Created role: %s (id=%s)", nombre, rol.id)

        # ── Create permissions (idempotent) ──────────────────────────
        created_permisos: dict[str, Permiso] = {}

        for pdef in PERMISOS:
            stmt = select(Permiso).where(
                Permiso.tenant_id == tid,
                Permiso.codigo == pdef["codigo"],
                Permiso.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("Permiso '%s' already exists — skipping.", pdef["codigo"])
                created_permisos[pdef["codigo"]] = existing
            else:
                permiso = Permiso(
                    tenant_id=tid,
                    codigo=pdef["codigo"],
                    modulo=pdef["modulo"],
                    descripcion=pdef["descripcion"],
                )
                session.add(permiso)
                await session.flush()
                await session.refresh(permiso)
                created_permisos[pdef["codigo"]] = permiso
                logger.info("Created permiso: %s (id=%s)", pdef["codigo"], permiso.id)

        # ── Create Rol↔Permiso matrix entries (idempotent) ──────────
        for nombre, perm_scopes in PERMISSION_MATRIX.items():
            rol = created_roles[nombre]
            for codigo, scope in perm_scopes.items():
                permiso = created_permisos[codigo]
                stmt = select(RolPermiso).where(
                    RolPermiso.tenant_id == tid,
                    RolPermiso.rol_id == rol.id,
                    RolPermiso.permiso_id == permiso.id,
                    RolPermiso.deleted_at.is_(None),
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    continue

                rp = RolPermiso(
                    tenant_id=tid,
                    rol_id=rol.id,
                    permiso_id=permiso.id,
                    scope=scope,
                )
                session.add(rp)
                await session.flush()
                logger.debug("Linked %s -> %s (scope=%s)", nombre, codigo, scope)

        # ── Assign ADMIN role to the seed admin user ──────────────────
        from app.models.user import User  # noqa: PLC0415

        stmt = select(User).where(
            User.tenant_id == tid,
            User.email == ADMIN_EMAIL,
            User.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        admin_user = result.scalar_one_or_none()

        if admin_user is None:
            logger.warning(
                "Admin user '%s' not found. Run seed_admin.py first. "
                "Skipping ADMIN role assignment.",
                ADMIN_EMAIL,
            )
        else:
            admin_rol = created_roles["ADMIN"]
            stmt = select(UserRol).where(
                UserRol.tenant_id == tid,
                UserRol.user_id == admin_user.id,
                UserRol.rol_id == admin_rol.id,
                UserRol.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("User '%s' already has role ADMIN — skipping.", ADMIN_EMAIL)
            else:
                user_rol = UserRol(
                    tenant_id=tid,
                    user_id=admin_user.id,
                    rol_id=admin_rol.id,
                )
                session.add(user_rol)
                logger.info("Assigned ADMIN role to user '%s'.", ADMIN_EMAIL)

        await session.commit()
        logger.info(
            "Rol↔Permiso matrix complete: %d roles, %d permissions",
            len(created_roles), len(created_permisos),
        )
        logger.info("Seed completed successfully.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(seed())
