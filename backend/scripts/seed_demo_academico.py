#!/usr/bin/env python3
"""Seed datos de demo académico para ejercitar C-22 en el tenant tupad.

Crea (idempotente — skip si ya existe):
  1. Carrera "Tecnicatura en Programación" (código TUP)
  2. Cohorte "2026" bajo esa carrera
  3. Materia "Programación IV" (código PROG-IV)
  4. Usuario PROFESOR  →  profesor@tupad.edu.ar / Profesor123!
  5. UserRol: asigna el rol PROFESOR al usuario
  6. Asignación docente: PROFESOR → Programación IV / TUP / 2026, desde 2026-01-01
  7. VersionPadron activa para Programación IV + cohorte 2026
  8. 8 EntradaPadron (alumnos ficticios con nombre/apellidos/comision)

NO carga calificaciones — se importan desde la UI (objetivo de C-22).

Prerequisitos:
  - seed_tenant.py  (debe existir el tenant "tupad")
  - seed_permissions.py (debe existir el rol PROFESOR)

Usage:
    cd backend
    python scripts/seed_demo_academico.py
"""

import asyncio
import logging
import os
from datetime import date

from sqlalchemy import select

from app.core.database import AsyncSession, engine, init_engine
from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.models.asignacion import Asignacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.entrada_padron import EntradaPadron
from app.models.materia import Materia
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol
from app.models.version_padron import VersionPadron

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("seed_demo_academico")

# ── Configuración (sobreescribible por env) ───────────────────────────────
TENANT_CODE       = os.getenv("SEED_TENANT_CODE",       "tupad")
PROFESOR_EMAIL    = os.getenv("SEED_PROFESOR_EMAIL",    "profesor@tupad.edu.ar")
PROFESOR_PASSWORD = os.getenv("SEED_PROFESOR_PASSWORD", "Profesor123!")

# Padrón ficticio de 8 alumnos: (nombre, apellidos, email, comision)
ALUMNOS = [
    ("Ana",      "García",    "ana.garcia@demo.com",       "Comisión A"),
    ("Bruno",    "Martínez",  "bruno.martinez@demo.com",   "Comisión A"),
    ("Carla",    "Romero",    "carla.romero@demo.com",     "Comisión A"),
    ("Diego",    "López",     "diego.lopez@demo.com",      "Comisión A"),
    ("Elena",    "Sánchez",   "elena.sanchez@demo.com",    "Comisión B"),
    ("Franco",   "Torres",    "franco.torres@demo.com",    "Comisión B"),
    ("Gabriela", "Ruiz",      "gabriela.ruiz@demo.com",    "Comisión B"),
    ("Hernán",   "Vega",      "hernan.vega@demo.com",      "Comisión B"),
]


async def seed() -> None:
    init_engine()
    if engine is None:
        raise RuntimeError("Engine not initialised")

    async with AsyncSession(engine) as session:

        # ── 0. Tenant ────────────────────────────────────────────────────
        result = await session.execute(
            select(Tenant).where(
                Tenant.codigo == TENANT_CODE,
                Tenant.deleted_at.is_(None),
            )
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            logger.error(
                "Tenant '%s' no encontrado. Ejecutá seed_tenant.py primero.", TENANT_CODE
            )
            return
        tid = tenant.id
        logger.info("Tenant: %s  id=%s", tenant.codigo, tid)

        # ── 1. Carrera ───────────────────────────────────────────────────
        from app.repositories.carrera_repository import CarreraRepository  # noqa: PLC0415
        carrera_repo = CarreraRepository(session, tid)
        carrera = await carrera_repo.get_by_codigo("TUP")
        if carrera is None:
            carrera = Carrera(
                tenant_id=tid,
                codigo="TUP",
                nombre="Tecnicatura en Programación",
            )
            session.add(carrera)
            await session.flush()
            await session.refresh(carrera)
            logger.info("Carrera CREADA:  %s  id=%s", carrera.nombre, carrera.id)
        else:
            logger.info("Carrera ya existe — skip  id=%s", carrera.id)

        # ── 2. Cohorte ───────────────────────────────────────────────────
        from app.repositories.cohorte_repository import CohorteRepository  # noqa: PLC0415
        cohorte_repo = CohorteRepository(session, tid)
        cohorte = await cohorte_repo.get_by_nombre_carrera("2026", carrera.id)
        if cohorte is None:
            cohorte = Cohorte(
                tenant_id=tid,
                carrera_id=carrera.id,
                nombre="2026",
                anio=2026,
                vig_desde=date(2026, 1, 1),
            )
            session.add(cohorte)
            await session.flush()
            await session.refresh(cohorte)
            logger.info("Cohorte CREADA:  %s  id=%s", cohorte.nombre, cohorte.id)
        else:
            logger.info("Cohorte ya existe — skip  id=%s", cohorte.id)

        # ── 3. Materia ───────────────────────────────────────────────────
        from app.repositories.materia_repository import MateriaRepository  # noqa: PLC0415
        materia_repo = MateriaRepository(session, tid)
        materia = await materia_repo.get_by_codigo("PROG-IV")
        if materia is None:
            materia = Materia(
                tenant_id=tid,
                codigo="PROG-IV",
                nombre="Programación IV",
            )
            session.add(materia)
            await session.flush()
            await session.refresh(materia)
            logger.info("Materia CREADA:  %s  id=%s", materia.nombre, materia.id)
        else:
            logger.info("Materia ya existe — skip  id=%s", materia.id)

        # ── 4. Usuario PROFESOR ──────────────────────────────────────────
        from app.repositories.user_repository import UserRepository  # noqa: PLC0415
        user_repo = UserRepository(session, tid)
        profesor = await user_repo.get_by_email_hash(PROFESOR_EMAIL)
        if profesor is None:
            profesor = User(
                tenant_id=tid,
                email_cifrado=encrypt(PROFESOR_EMAIL),
                email_hash=hmac_email(PROFESOR_EMAIL),
                password_hash=hash_password(PROFESOR_PASSWORD),
                nombre="Carlos",
                apellidos="Mendoza",
                is_active=True,
                is_2fa_enabled=False,
            )
            session.add(profesor)
            await session.flush()
            await session.refresh(profesor)
            logger.info("Usuario PROFESOR CREADO:  id=%s", profesor.id)
        else:
            logger.info("Usuario PROFESOR ya existe — skip  id=%s", profesor.id)

        # ── 5. Rol PROFESOR (creado por seed_permissions.py) ────────────
        from app.repositories.rol_repository import RolRepository  # noqa: PLC0415
        rol_repo = RolRepository(session, tid)
        rol_profesor = await rol_repo.find_by_nombre("PROFESOR")
        if rol_profesor is None:
            logger.error(
                "Rol PROFESOR no encontrado en tenant '%s'. "
                "Ejecutá seed_permissions.py primero.",
                TENANT_CODE,
            )
            return
        logger.info("Rol PROFESOR:  id=%s", rol_profesor.id)

        # ── 6. UserRol: asignar rol PROFESOR al usuario ──────────────────
        existing_ur = (
            await session.execute(
                select(UserRol).where(
                    UserRol.tenant_id == tid,
                    UserRol.user_id == profesor.id,
                    UserRol.rol_id == rol_profesor.id,
                    UserRol.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing_ur is None:
            session.add(UserRol(
                tenant_id=tid,
                user_id=profesor.id,
                rol_id=rol_profesor.id,
            ))
            await session.flush()
            logger.info("UserRol PROFESOR ASIGNADO")
        else:
            logger.info("UserRol PROFESOR ya existe — skip")

        # ── 7. Asignación docente ────────────────────────────────────────
        existing_asig = (
            await session.execute(
                select(Asignacion).where(
                    Asignacion.tenant_id == tid,
                    Asignacion.usuario_id == profesor.id,
                    Asignacion.rol_id == rol_profesor.id,
                    Asignacion.materia_id == materia.id,
                    Asignacion.cohorte_id == cohorte.id,
                    Asignacion.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing_asig is None:
            session.add(Asignacion(
                tenant_id=tid,
                usuario_id=profesor.id,
                rol_id=rol_profesor.id,
                materia_id=materia.id,
                carrera_id=carrera.id,
                cohorte_id=cohorte.id,
                desde=date(2026, 1, 1),
            ))
            await session.flush()
            logger.info("Asignación docente CREADA")
        else:
            logger.info("Asignación docente ya existe — skip  id=%s", existing_asig.id)

        # ── 8. Padrón: VersionPadron + 8 EntradaPadron ───────────────────
        from app.repositories.version_padron_repository import VersionPadronRepository  # noqa: PLC0415
        vp_repo = VersionPadronRepository(session, tid)
        version = await vp_repo.get_active(materia.id, cohorte.id)
        if version is None:
            version = VersionPadron(
                tenant_id=tid,
                materia_id=materia.id,
                cohorte_id=cohorte.id,
                cargado_por=profesor.id,
                activa=True,
            )
            session.add(version)
            await session.flush()
            await session.refresh(version)
            logger.info("VersionPadron CREADA:  id=%s", version.id)

            for nombre, apellidos, email, comision in ALUMNOS:
                session.add(EntradaPadron(
                    tenant_id=tid,
                    version_id=version.id,
                    nombre=nombre,
                    apellidos=apellidos,
                    email_cifrado=encrypt(email),
                    email_hash=hmac_email(email),
                    comision=comision,
                ))
            await session.flush()
            logger.info("Padrón CARGADO: %d alumnos", len(ALUMNOS))
        else:
            logger.info(
                "VersionPadron activa ya existe — skip padrón  id=%s", version.id
            )

        # ── Commit único ─────────────────────────────────────────────────
        await session.commit()
        logger.info("✓ seed_demo_academico completado.")
        logger.info("")
        logger.info("  Acceso PROFESOR:")
        logger.info("    Email:    %s", PROFESOR_EMAIL)
        logger.info("    Password: %s", PROFESOR_PASSWORD)
        logger.info("")
        logger.info("  Estructura creada:")
        logger.info("    Carrera: Tecnicatura en Programación (TUP)")
        logger.info("    Cohorte: 2026")
        logger.info("    Materia: Programación IV (PROG-IV)")
        logger.info("    Alumnos: %d en padrón (4 Comisión A / 4 Comisión B)", len(ALUMNOS))


if __name__ == "__main__":
    asyncio.run(seed())
