# C-09 — Design Decisions

## D-C09-1: VersionPadron con índice único parcial (unicidad de versión activa en DB)

**Decisión**: la restricción "solo una versión activa por (tenant_id, materia_id, cohorte_id)"
se enforcea en la DB con un índice único parcial, no solo en el servicio.

```sql
CREATE UNIQUE INDEX uq_version_padron_activa
  ON version_padron (tenant_id, materia_id, cohorte_id)
  WHERE activa = TRUE AND deleted_at IS NULL;
```

**Justificación**: sin este índice, una condición de carrera entre dos requests simultáneos podría
crear dos versiones activas. El índice parcial fuerza unicidad sin afectar versiones inactivas/archivadas.

**Flujo de activación** (en la misma transacción):
```python
# 1. Desactivar versión anterior
await session.execute(
    update(VersionPadron)
    .where(
        VersionPadron.tenant_id == tenant_id,
        VersionPadron.materia_id == materia_id,
        VersionPadron.cohorte_id == cohorte_id,
        VersionPadron.activa == True,
        VersionPadron.deleted_at.is_(None),
    )
    .values(activa=False)
)
# 2. Crear nueva versión activa
nueva = VersionPadron(activa=True, ...)
session.add(nueva)
await session.flush()
# 3. Bulk insert EntradaPadron
```

---

## D-C09-2: EntradaPadron.email = EncryptedString + email_hash (reutiliza patrón C-07)

**Decisión**: `EntradaPadron.email_cifrado` usa el mismo `EncryptedString` TypeDecorator y
`email_hash = hmac_email(email)` que `User.email_cifrado`/`User.email_hash` de C-07.

**Por qué el mismo patrón**:
- Consistencia: mismo mecanismo de cifrado en todo el sistema.
- Permite el auto-link: `entrada.email_hash == user.email_hash` → mismo valor determinístico.
- Ya está implementado y testeado en C-07.

**Campos en entrada_padron**:

| Campo | Tipo DB | Notas |
|-------|---------|-------|
| `email_cifrado` | TEXT NOT NULL | AES-256-GCM via `EncryptedString` TypeDecorator |
| `email_hash` | VARCHAR(64) NOT NULL | HMAC-SHA256 del email normalizado |

El ORM recibe `email_cifrado = plaintext` — el TypeDecorator cifra en `process_bind_param`.
Para insertar en raw SQL (seeds, migrations de datos) se llama `encrypt(email)` y `hmac_email(email)` explícitamente.

**No hay UNIQUE constraint en (version_id, email_hash)** en la DB: la unicidad dentro de una versión
se garantiza en el servicio (el parser deduplica por email antes de bulk-insert). Un constraint de DB
introduciría complejidad innecesaria en el bulk-insert transaccional.

---

## D-C09-3: Auto-link email → usuario_id al importar

**Decisión**: durante el import, cada entrada del padrón intenta vincularse a un `User` existente
en el mismo tenant comparando `email_hash`.

```python
async def _resolve_usuario_id(email: str, tenant_id: UUID, session: AsyncSession) -> UUID | None:
    h = hmac_email(email)
    result = await session.execute(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.email_hash == h,
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
```

**Comportamiento**:
- Si hay match → `EntradaPadron.usuario_id = user.id`
- Si no hay match → `EntradaPadron.usuario_id = None` (el alumno aún no tiene cuenta)
- El auto-link NO falla si el usuario no existe — el padrón se importa igual.

**Re-linking**: el auto-link se ejecuta solo en el momento de la importación. Si el usuario se
crea después, el link no se actualiza automáticamente en C-09 (queda como mejora futura en C-10).

---

## D-C09-4: MoodleWSClient detrás de Protocol (mockeable en tests)

**Decisión**: el cliente de Moodle WS se abstrae como un Protocol Python (duck typing estático)
inyectado como dependencia FastAPI.

```python
# backend/app/integrations/moodle_ws.py

from typing import Protocol, runtime_checkable

class MoodleParticipant(TypedDict):
    nombre: str
    apellidos: str
    email: str
    comision: str | None
    regional: str | None

@runtime_checkable
class MoodleWSClientProtocol(Protocol):
    async def get_participants(self, course_id: str) -> list[MoodleParticipant]: ...

class MoodleWSError(Exception):
    """Raised by MoodleWSClient when the WS is unavailable. Maps to HTTP 502."""

class MoodleWSClient:
    """Concrete implementation using httpx + Moodle Web Services REST API."""
    def __init__(self, base_url: str, token: str) -> None: ...
    async def get_participants(self, course_id: str) -> list[MoodleParticipant]: ...
```

**Inyección vía FastAPI dependency**:
```python
def get_moodle_client() -> MoodleWSClientProtocol:
    return MoodleWSClient(
        base_url=settings.MOODLE_BASE_URL,
        token=settings.MOODLE_WS_TOKEN,
    )
```

**En tests**: `app.dependency_overrides[get_moodle_client] = lambda: FakeMoodleWSClient(participants=[...])`

**Manejo de errores**: cualquier excepción de red o respuesta de error del WS se captura en el
cliente concreto y relanza como `MoodleWSError`. El router la captura y retorna HTTP 502.

---

## D-C09-5: Import en dos pasos — preview luego confirm

**Decisión**: el import de archivo soporta un modo `preview` (query param `?preview=true`) que
parsea el archivo y devuelve las filas sin escribir en DB.

```
POST /api/v1/padron/{materia_id}/cohortes/{cohorte_id}/importar?preview=true
  → 200 PadronPreview { total: N, entradas: [...rows], vinculados: K, warnings: [...] }

POST /api/v1/padron/{materia_id}/cohortes/{cohorte_id}/importar?preview=false (default)
  → 201 VersionPadronResponse { version_id, activa: true, total_entradas: N, entradas_vinculadas: K }
```

**Sin endpoint separado de "confirm"**: el usuario puede llamar directamente a `preview=false`
sin previa llamada a `preview=true`. La preview es una conveniencia UX, no un paso requerido.

**Warnings**: el parser emite advertencias (no errores) sobre filas con datos faltantes opcionales
(comision null, regional null) para que el usuario pueda revisar el contenido antes de confirmar.

---

## D-C09-6: Vaciar = soft-delete de VersionPadron (EntradaPadron queda para audit)

**Decisión**: la operación "vaciar" soft-delete la `VersionPadron` activa
(`activa = False`, `deleted_at = now()`). Las filas de `EntradaPadron` NO se soft-delete.

**Justificación**:
- Las entradas quedan accesibles para auditoría (RN-23: toda acción significativa queda registrada).
- La versión eliminada no aparece en ninguna consulta activa (todos los queries filtran por
  `activa=True AND deleted_at IS NULL` en `VersionPadron`).
- Las entradas son inaccesibles vía API una vez que su versión está eliminada.

**Scope de vaciar (RN-04)**:
- PROFESOR (scope=own): solo puede vaciar si `version.cargado_por == current_user.id`.
  Si la versión activa fue cargada por otro usuario → 403 Forbidden.
- COORDINADOR/ADMIN (scope=all): puede vaciar cualquier versión activa del tenant.

---

## D-C09-7: Parseo de archivo — mapeo de columnas por alias

**Decisión**: el parser acepta múltiples nombres de columna (case-insensitive, trim) para cada campo.
Esto hace el import robusto frente a distintos formatos de export del LMS.

| Campo interno | Aliases aceptados |
|---------------|-------------------|
| `nombre` | `nombre`, `first_name`, `firstname`, `name` |
| `apellidos` | `apellidos`, `apellido`, `last_name`, `lastname`, `surname` |
| `email` | `email`, `correo`, `mail`, `e-mail`, `e mail` |
| `comision` | `comision`, `comisión`, `grupo`, `group`, `section` |
| `regional` | `regional`, `sede`, `region` |

Si `nombre`, `apellidos` o `email` faltan para una fila → la fila se descarta con warning.
Si el archivo no tiene ninguna de las columnas esperadas para `email` → error 400 (archivo inválido).

---

## Migración 007 — Resumen

```
revision = "[a1b2c3d4e5f6]_007_version_padron"
down_revision = "c6d7e8f9a0b1"   ← C-07 (006 usuario_pii_asignacion)

upgrade():
  op.create_table("version_padron",
    id UUID PK,
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    materia_id UUID FK→materia RESTRICT NOT NULL,
    cohorte_id UUID FK→cohorte RESTRICT NOT NULL,
    cargado_por UUID FK→user RESTRICT NOT NULL,
    cargado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
  )
  # trigger updated_at en version_padron
  # Índice único parcial (D-C09-1):
  CREATE UNIQUE INDEX uq_version_padron_activa
    ON version_padron (tenant_id, materia_id, cohorte_id)
    WHERE activa = TRUE AND deleted_at IS NULL;
  CREATE INDEX idx_version_padron_materia ON version_padron(materia_id) WHERE deleted_at IS NULL;
  CREATE INDEX idx_version_padron_cohorte ON version_padron(cohorte_id) WHERE deleted_at IS NULL;

  op.create_table("entrada_padron",
    id UUID PK,
    version_id UUID FK→version_padron RESTRICT NOT NULL,
    tenant_id UUID FK→tenant CASCADE NOT NULL,
    usuario_id UUID FK→user SET NULL NULL,
    nombre VARCHAR(255) NOT NULL,
    apellidos VARCHAR(255) NOT NULL,
    email_cifrado TEXT NOT NULL,
    email_hash VARCHAR(64) NOT NULL,
    comision VARCHAR(255) NULL,
    regional VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
  )
  # trigger updated_at en entrada_padron
  CREATE INDEX idx_entrada_padron_version ON entrada_padron(version_id) WHERE deleted_at IS NULL;
  CREATE INDEX idx_entrada_padron_email_hash ON entrada_padron(tenant_id, email_hash) WHERE deleted_at IS NULL;
  CREATE INDEX idx_entrada_padron_usuario ON entrada_padron(usuario_id)
    WHERE deleted_at IS NULL AND usuario_id IS NOT NULL;

downgrade():
  op.drop_table("entrada_padron")
  op.drop_table("version_padron")
```

---

## Open Questions para C-09

| ID | Pregunta | Impacto |
|----|----------|---------|
| OQ-C09-1 | ¿El campo `comision` en EntradaPadron es libre o FK a alguna entidad? | KB no define entidad Comisión separada (PA-07 pendiente). Por ahora: VARCHAR libre. |
| OQ-C09-2 | ¿La sync nocturna de Moodle es un background worker en C-09 o solo el on-demand? | CHANGES.md menciona "sync nocturna". En C-09 se implementa solo el endpoint on-demand; el worker nocturno va en C-11 (worker). |
| OQ-C09-3 | ¿Qué `course_id` de Moodle corresponde a qué `materia_id` en el sistema? | Se necesita un campo `moodle_course_id` en la tabla `materia`. La migración 007 lo puede agregar como nullable, o se puede diferir a C-10. Propuesta: agregar en 007 para tener la FK lista. |
| OQ-C09-4 | ¿La preview retorna las filas completas (con email) o solo estadísticas? | Por privacidad, la preview retorna nombre+apellidos+comision pero NO el email plaintext. El email solo se almacena cifrado. |
