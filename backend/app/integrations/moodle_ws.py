"""Moodle Web Services client.

Provides:
- MoodleParticipant: TypedDict for a single participant row
- MoodleWSError: raised on any WS failure (maps to HTTP 502 in router)
- MoodleWSClientProtocol: Protocol (duck-typing interface) for injection / testing
- MoodleWSClient: concrete implementation using httpx
- FakeMoodleWSClient: injectable fake for tests (no HTTP calls)
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable

import httpx


class MoodleParticipant(TypedDict):
    nombre: str
    apellidos: str
    email: str
    comision: str | None
    regional: str | None


class MoodleWSError(Exception):
    """Raised by MoodleWSClient when Moodle WS is unavailable or returns an error.

    The router catches this and returns HTTP 502.
    """


@runtime_checkable
class MoodleWSClientProtocol(Protocol):
    async def get_participants(self, course_id: str) -> list[MoodleParticipant]:
        """Fetch enrolled participants for a Moodle course.

        Raises:
            MoodleWSError: on network failure or Moodle API error.
        """
        ...


class MoodleWSClient:
    """Concrete Moodle WS client using httpx (async)."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    async def get_participants(self, course_id: str) -> list[MoodleParticipant]:
        url = f"{self._base_url}/webservice/rest/server.php"
        params = {
            "wstoken": self._token,
            "wsfunction": "core_enrol_get_enrolled_users",
            "moodlewsrestformat": "json",
            "courseid": course_id,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise MoodleWSError(f"Moodle WS no disponible: {exc}") from exc

        if isinstance(data, dict) and "exception" in data:
            raise MoodleWSError(f"Moodle API error: {data.get('message', 'desconocido')}")

        return [_map_participant(p) for p in data]


def _map_participant(raw: dict) -> MoodleParticipant:
    return MoodleParticipant(
        nombre=raw.get("firstname") or "",
        apellidos=raw.get("lastname") or "",
        email=raw.get("email") or "",
        comision=(raw.get("groups") or [{}])[0].get("name") if raw.get("groups") else None,
        regional=None,
    )


class FakeMoodleWSClient:
    """Injectable fake for tests — makes no HTTP calls."""

    def __init__(
        self,
        participants: list[MoodleParticipant] | None = None,
        raises: bool = False,
    ) -> None:
        self._participants = participants or []
        self._raises = raises

    async def get_participants(self, course_id: str) -> list[MoodleParticipant]:
        if self._raises:
            raise MoodleWSError("Moodle WS simulado no disponible")
        return self._participants
