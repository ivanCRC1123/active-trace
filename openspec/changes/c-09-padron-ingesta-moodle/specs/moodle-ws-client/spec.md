# Spec: MoodleWSClient

## Propósito

Abstracción del cliente HTTP para el Moodle Web Services REST API. Permite:
1. Inyectar un fake en tests (sin Moodle vivo).
2. Mapear errores de red a `MoodleWSError` → HTTP 502 en el router.
3. Separar la lógica de integración del servicio de padrón.

## Protocol (interfaz abstracta)

```python
# backend/app/integrations/moodle_ws.py

from typing import Protocol, TypedDict, runtime_checkable

class MoodleParticipant(TypedDict):
    nombre: str
    apellidos: str
    email: str
    comision: str | None
    regional: str | None

class MoodleWSError(Exception):
    """Raised when Moodle WS is unavailable or returns an error.
    Maps to HTTP 502 in the router."""

@runtime_checkable
class MoodleWSClientProtocol(Protocol):
    async def get_participants(self, course_id: str) -> list[MoodleParticipant]:
        """Fetch participants for a Moodle course.

        Raises:
            MoodleWSError: on any network failure or Moodle API error.
        """
        ...
```

## Implementación concreta

```python
import httpx

class MoodleWSClient:
    """Concrete Moodle WS client using httpx."""

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
            raise MoodleWSError(f"Moodle API error: {data.get('message', 'unknown')}")

        return [_map_participant(p) for p in data]


def _map_participant(raw: dict) -> MoodleParticipant:
    full = raw.get("fullname", "")
    parts = full.split(" ", 1)
    nombre = parts[0] if parts else ""
    apellidos = parts[1] if len(parts) > 1 else ""
    return MoodleParticipant(
        nombre=raw.get("firstname") or nombre,
        apellidos=raw.get("lastname") or apellidos,
        email=raw.get("email", ""),
        comision=raw.get("groups", [{}])[0].get("name") if raw.get("groups") else None,
        regional=None,
    )
```

## Dependency FastAPI

```python
# backend/app/core/dependencies.py (adición)
from app.integrations.moodle_ws import MoodleWSClient, MoodleWSClientProtocol
from app.core.config import settings

def get_moodle_client() -> MoodleWSClientProtocol:
    return MoodleWSClient(
        base_url=settings.MOODLE_BASE_URL,
        token=settings.MOODLE_WS_TOKEN,
    )
```

Settings nuevas requeridas en `.env` / `settings.py`:
- `MOODLE_BASE_URL`: URL base del Moodle del tenant (ej. `https://moodle.uni.edu`)
- `MOODLE_WS_TOKEN`: token de acceso a WS (generado en Moodle Admin → Site admin → Users → Web services)

## Fake para tests

```python
class FakeMoodleWSClient:
    """Inyectable en tests — no hace requests HTTP."""

    def __init__(self, participants: list[MoodleParticipant] | None = None, raises: bool = False) -> None:
        self._participants = participants or []
        self._raises = raises

    async def get_participants(self, course_id: str) -> list[MoodleParticipant]:
        if self._raises:
            raise MoodleWSError("Moodle WS simulado no disponible")
        return self._participants
```

## Escenarios

### Sync exitosa
```
DADO que FakeMoodleWSClient retorna 10 participantes
Y la materia tiene moodle_course_id="42"
CUANDO POST /api/v1/padron/{mid}/cohortes/{cid}/sincronizar-moodle
ENTONCES 201 con PadronImportResult.total_importadas=10
```

### Moodle no disponible → 502
```
DADO que FakeMoodleWSClient lanza MoodleWSError
CUANDO POST /api/v1/padron/{mid}/cohortes/{cid}/sincronizar-moodle
ENTONCES 502 { "detail": "Moodle WS no disponible", "retry": true }
```

### Materia sin moodle_course_id → 400
```
DADO que la materia NO tiene moodle_course_id configurado
CUANDO POST /api/v1/padron/{mid}/cohortes/{cid}/sincronizar-moodle
ENTONCES 400 "la materia no tiene moodle_course_id configurado"
```

## Settings nuevas

```python
# backend/app/core/config.py (adición)
MOODLE_BASE_URL: str = ""     # vacío = integración deshabilitada
MOODLE_WS_TOKEN: str = ""
```

Si `MOODLE_BASE_URL` está vacío y se llama al endpoint de sync → 503 "integración Moodle no configurada".
