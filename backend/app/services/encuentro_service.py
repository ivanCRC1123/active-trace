"""EncuentroService — C-13 épica 6 (F6.1–F6.5).

Scoping "propio":
  - scope="own" (PROFESOR): solo slots/instancias donde asignacion_id pertenece al usuario.
  - scope="all" (TUTOR, COORDINADOR, ADMIN): todo el tenant.

D-C13-1: fecha_inicio DEBE caer en dia_semana (Opción A, validación estricta → 422).
D-C13-2: reprogramar = cancelar instancia vieja + crear nueva (no hay estado Reprogramado).
D-C13-3: asignacion_id SIEMPRE poblado en InstanciaEncuentro (denormalizado de slot).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import ENCUENTRO_CREAR, ENCUENTRO_EDITAR_INSTANCIA
from app.models.asignacion import Asignacion
from app.models.instancia_encuentro import InstanciaEncuentro
from app.models.materia import Materia
from app.repositories.instancia_repository import InstanciaRepository
from app.repositories.slot_repository import SlotRepository
from app.schemas.auth import CurrentUser
from app.schemas.encuentros import (
    FragmentoLMSResponse,
    InstanciaResponse,
    InstanciaUpdate,
    SlotConInstanciasResponse,
    SlotCreate,
    SlotResponse,
)
from app.services.audit_service import AuditService

# Mapeo dia_semana (español) → isoweekday (Lunes=1 … Domingo=7)
_DIA_ISO: dict[str, int] = {
    "Lunes": 1,
    "Martes": 2,
    "Miércoles": 3,
    "Jueves": 4,
    "Viernes": 5,
    "Sábado": 6,
    "Domingo": 7,
}

_MES_ES: dict[int, str] = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def _slot_to_response(slot, instancias: list[InstanciaEncuentro]) -> SlotConInstanciasResponse:
    modo = "recurrente" if slot.cant_semanas > 0 else "unico"
    return SlotConInstanciasResponse(
        id=slot.id,
        asignacion_id=slot.asignacion_id,
        materia_id=slot.materia_id,
        titulo=slot.titulo,
        hora=slot.hora,
        modo=modo,
        dia_semana=slot.dia_semana,
        fecha_inicio=slot.fecha_inicio,
        cant_semanas=slot.cant_semanas,
        fecha_unica=slot.fecha_unica,
        meet_url=slot.meet_url,
        vig_desde=slot.vig_desde,
        vig_hasta=slot.vig_hasta,
        created_at=slot.created_at,
        instancias=[_inst_to_response(i) for i in instancias],
    )


def _slot_list_response(slot) -> SlotResponse:
    modo = "recurrente" if slot.cant_semanas > 0 else "unico"
    return SlotResponse(
        id=slot.id,
        asignacion_id=slot.asignacion_id,
        materia_id=slot.materia_id,
        titulo=slot.titulo,
        hora=slot.hora,
        modo=modo,
        dia_semana=slot.dia_semana,
        fecha_inicio=slot.fecha_inicio,
        cant_semanas=slot.cant_semanas,
        fecha_unica=slot.fecha_unica,
        meet_url=slot.meet_url,
        vig_desde=slot.vig_desde,
        vig_hasta=slot.vig_hasta,
        created_at=slot.created_at,
    )


def _inst_to_response(inst: InstanciaEncuentro) -> InstanciaResponse:
    return InstanciaResponse(
        id=inst.id,
        slot_id=inst.slot_id,
        asignacion_id=inst.asignacion_id,
        materia_id=inst.materia_id,
        fecha=inst.fecha,
        hora=inst.hora,
        titulo=inst.titulo,
        estado=inst.estado,
        meet_url=inst.meet_url,
        video_url=inst.video_url,
        comentario=inst.comentario,
        created_at=inst.created_at,
        updated_at=inst.updated_at,
    )


class EncuentroService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _slots(self, tenant_id: UUID) -> SlotRepository:
        return SlotRepository(self._session, tenant_id)

    def _instancias(self, tenant_id: UUID) -> InstanciaRepository:
        return InstanciaRepository(self._session, tenant_id)

    def _audit(self) -> AuditService:
        return AuditService(self._session)

    async def _get_asignacion_ids(self, usuario_id: UUID, tenant_id: UUID) -> list[UUID]:
        """IDs de asignaciones activas del usuario en el tenant."""
        stmt = select(Asignacion.id).where(
            Asignacion.usuario_id == usuario_id,
            Asignacion.tenant_id == tenant_id,
            Asignacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _validar_modo(data: SlotCreate) -> None:
        if data.modo == "recurrente":
            if not data.dia_semana or not data.fecha_inicio or not data.cant_semanas:
                raise ValueError("Modo recurrente requiere dia_semana, fecha_inicio y cant_semanas")
            if data.cant_semanas <= 0:
                raise ValueError("cant_semanas debe ser > 0 en modo recurrente")
            if data.cant_semanas > 52:
                raise ValueError("cant_semanas no puede superar 52")
            if data.fecha_unica is not None:
                raise ValueError("fecha_unica debe ser null en modo recurrente")
        else:
            if not data.fecha_unica:
                raise ValueError("Modo único requiere fecha_unica")
            if data.dia_semana or data.fecha_inicio or data.cant_semanas:
                raise ValueError("dia_semana, fecha_inicio y cant_semanas deben ser null en modo único")

    @staticmethod
    def _validar_fecha_dia(fecha: date, dia_semana: str) -> None:
        expected = _DIA_ISO.get(dia_semana)
        if expected is None:
            raise ValueError(f"dia_semana inválido: {dia_semana!r}")
        if fecha.isoweekday() != expected:
            raise ValueError(
                f"fecha_inicio {fecha} no cae en {dia_semana} "
                f"(es el día {fecha.isoweekday()} ISO, esperado {expected})"
            )

    @staticmethod
    def _generar_instancias(
        slot_id: UUID,
        tenant_id: UUID,
        asignacion_id: UUID,
        materia_id: UUID,
        titulo: str,
        hora,
        meet_url: str | None,
        modo: str,
        fecha_inicio: date | None,
        cant_semanas: int,
        fecha_unica: date | None,
    ) -> list[InstanciaEncuentro]:
        if modo == "recurrente":
            fechas: list[date] = [
                fecha_inicio + timedelta(weeks=i)  # type: ignore[operator]
                for i in range(cant_semanas)
            ]
        else:
            fechas = [fecha_unica]  # type: ignore[list-item]

        return [
            InstanciaEncuentro(
                tenant_id=tenant_id,
                slot_id=slot_id,
                asignacion_id=asignacion_id,
                materia_id=materia_id,
                fecha=f,
                hora=hora,
                titulo=titulo,
                estado="Programado",
                meet_url=meet_url,
            )
            for f in fechas
        ]

    async def _assert_asignacion_propia(
        self, asignacion_id: UUID, usuario_id: UUID, tenant_id: UUID
    ) -> None:
        ids = await self._get_asignacion_ids(usuario_id, tenant_id)
        if asignacion_id not in ids:
            raise PermissionError("asignacion_no_propia")

    # ── F6.1 / F6.2 — Crear slot ────────────────────────────────────────────

    async def crear_slot(
        self, current_user: CurrentUser, data: SlotCreate, scope: str | None
    ) -> SlotConInstanciasResponse:
        self._validar_modo(data)
        if data.modo == "recurrente":
            self._validar_fecha_dia(data.fecha_inicio, data.dia_semana)  # type: ignore[arg-type]

        # PROFESOR(own): verifica que la asignacion_id sea suya
        if scope == "own":
            await self._assert_asignacion_propia(
                data.asignacion_id, current_user.user_id, current_user.tenant_id
            )

        slot_data = {
            "asignacion_id": data.asignacion_id,
            "materia_id": data.materia_id,
            "titulo": data.titulo,
            "hora": data.hora,
            "dia_semana": data.dia_semana,
            "fecha_inicio": data.fecha_inicio,
            "cant_semanas": data.cant_semanas or 0,
            "fecha_unica": data.fecha_unica,
            "meet_url": data.meet_url,
            "vig_desde": data.vig_desde,
            "vig_hasta": data.vig_hasta,
        }
        slot = await self._slots(current_user.tenant_id).create(slot_data)

        instancias = self._generar_instancias(
            slot_id=slot.id,
            tenant_id=current_user.tenant_id,
            asignacion_id=data.asignacion_id,
            materia_id=data.materia_id,
            titulo=data.titulo,
            hora=data.hora,
            meet_url=data.meet_url,
            modo=data.modo,
            fecha_inicio=data.fecha_inicio,
            cant_semanas=data.cant_semanas or 0,
            fecha_unica=data.fecha_unica,
        )
        instancias = await self._instancias(current_user.tenant_id).create_bulk(instancias)

        await self._audit().log(
            current_user=current_user,
            accion=ENCUENTRO_CREAR,
            detalle={
                "slot_id": str(slot.id),
                "materia_id": str(data.materia_id),
                "modo": data.modo,
                "instancias_generadas": len(instancias),
            },
            materia_id=data.materia_id,
        )
        await self._session.commit()
        return _slot_to_response(slot, instancias)

    # ── F6.1/F6.5 — Listar slots ─────────────────────────────────────────────

    async def listar_slots(
        self, current_user: CurrentUser, scope: str | None, materia_id: UUID | None = None
    ) -> list[SlotResponse]:
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            slots = await self._slots(current_user.tenant_id).list_by_asignaciones(ids, materia_id)
        else:
            slots = await self._slots(current_user.tenant_id).list_all(materia_id)
        return [_slot_list_response(s) for s in slots]

    async def get_slot(
        self, current_user: CurrentUser, slot_id: UUID, scope: str | None
    ) -> SlotConInstanciasResponse:
        slot = await self._slots(current_user.tenant_id).get_by_id(slot_id)
        if slot is None:
            raise LookupError("slot_no_encontrado")
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            if slot.asignacion_id not in ids:
                raise PermissionError("slot_no_propio")
        instancias = await self._instancias(current_user.tenant_id).list_by_slot(slot_id)
        return _slot_to_response(slot, instancias)

    async def eliminar_slot(
        self, current_user: CurrentUser, slot_id: UUID, scope: str | None
    ) -> None:
        slot = await self._slots(current_user.tenant_id).get_by_id(slot_id)
        if slot is None:
            raise LookupError("slot_no_encontrado")
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            if slot.asignacion_id not in ids:
                raise PermissionError("slot_no_propio")
        # Cancela instancias Programado; Realizadas se conservan
        await self._instancias(current_user.tenant_id).cancel_by_slot(slot_id)
        await self._slots(current_user.tenant_id).soft_delete(slot_id)
        await self._session.commit()

    # ── F6.3 — Listar y editar instancias ────────────────────────────────────

    async def listar_instancias(
        self,
        current_user: CurrentUser,
        scope: str | None,
        materia_id: UUID | None = None,
        slot_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[InstanciaResponse]:
        repo = self._instancias(current_user.tenant_id)
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            insts = await repo.list_by_asignaciones(
                ids, materia_id, slot_id, estado, fecha_desde, fecha_hasta
            )
        else:
            insts = await repo.list_all(materia_id, slot_id, estado, fecha_desde, fecha_hasta)
        return [_inst_to_response(i) for i in insts]

    async def editar_instancia(
        self,
        current_user: CurrentUser,
        instancia_id: UUID,
        data: InstanciaUpdate,
        scope: str | None,
    ) -> InstanciaResponse:
        inst = await self._instancias(current_user.tenant_id).get_by_id(instancia_id)
        if inst is None:
            raise LookupError("instancia_no_encontrada")
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            if inst.asignacion_id not in ids:
                raise PermissionError("instancia_no_propia")

        cambios = {k: v for k, v in data.model_dump().items() if v is not None}
        if not cambios:
            return _inst_to_response(inst)

        inst = await self._instancias(current_user.tenant_id).update(instancia_id, cambios)
        await self._audit().log(
            current_user=current_user,
            accion=ENCUENTRO_EDITAR_INSTANCIA,
            detalle={
                "instancia_id": str(instancia_id),
                "campos_modificados": list(cambios.keys()),
                "nuevo_estado": cambios.get("estado"),
            },
            materia_id=inst.materia_id,  # type: ignore[union-attr]
        )
        await self._session.commit()
        return _inst_to_response(inst)  # type: ignore[arg-type]

    # ── F6.4 — Fragmento LMS ─────────────────────────────────────────────────

    async def fragmento_lms(
        self,
        current_user: CurrentUser,
        scope: str | None,
        materia_id: UUID,
        slot_id: UUID | None = None,
    ) -> FragmentoLMSResponse:
        # Nombre de la materia para el encabezado
        stmt = select(Materia).where(
            Materia.id == materia_id,
            Materia.tenant_id == current_user.tenant_id,
            Materia.deleted_at.is_(None),
        )
        materia = (await self._session.execute(stmt)).scalar_one_or_none()
        materia_nombre = materia.nombre if materia else str(materia_id)

        # Instancias visibles para el usuario (excluyendo Cancelado)
        repo = self._instancias(current_user.tenant_id)
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            programadas = await repo.list_by_asignaciones(ids, materia_id, slot_id, "Programado")
            realizadas = await repo.list_by_asignaciones(ids, materia_id, slot_id, "Realizado")
        else:
            programadas = await repo.list_all(materia_id, slot_id, "Programado")
            realizadas = await repo.list_all(materia_id, slot_id, "Realizado")

        lines: list[str] = [f"## Encuentros — {materia_nombre}"]

        if programadas:
            lines.append("\n### Programados")
            for inst in programadas:
                d = inst.fecha
                hora_str = inst.hora.strftime("%H:%M")
                fecha_str = f"{_dia_nombre(d)} {d.day:02d}-{_MES_ES[d.month]}-{d.year}"
                linea = f"- **{fecha_str} {hora_str}** — {inst.titulo}"
                if inst.meet_url:
                    linea += f" | [Sala virtual]({inst.meet_url})"
                lines.append(linea)

        if realizadas:
            lines.append("\n### Realizados")
            for inst in realizadas:
                d = inst.fecha
                hora_str = inst.hora.strftime("%H:%M")
                fecha_str = f"{_dia_nombre(d)} {d.day:02d}-{_MES_ES[d.month]}-{d.year}"
                linea = f"- **{fecha_str} {hora_str}** — {inst.titulo}"
                if inst.video_url:
                    linea += f" | [Grabación]({inst.video_url})"
                lines.append(linea)

        return FragmentoLMSResponse(fragmento="\n".join(lines))


_DIAS_ES: dict[int, str] = {
    1: "Lunes", 2: "Martes", 3: "Miércoles",
    4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo",
}


def _dia_nombre(d: date) -> str:
    return _DIAS_ES.get(d.isoweekday(), "")
