# Spec: Mensajería interna (F3.4, F11.2, FL-10)

## Entidades nuevas

Ver D-C20-3 en design.md para la discusión entre dos tablas vs self-ref.
Este spec asume **Opción A (recomendada): dos tablas**.

### E-MSG-H — HiloMensaje

```
HiloMensaje {
  id           : UUID PK          gen_random_uuid()
  tenant_id    : UUID FK→tenant   CASCADE NOT NULL
  asunto       : TEXT NOT NULL
  iniciador_id : UUID FK→user     RESTRICT NOT NULL   (quien creó el hilo)
  created_at   : TIMESTAMP        DEFAULT now()
  updated_at   : TIMESTAMP        DEFAULT now()       (se actualiza con cada mensaje nuevo)
  deleted_at   : TIMESTAMP nullable
}
```

### E-MSG-P — HiloParticipante (join table)

```
HiloParticipante {
  hilo_id          : UUID FK→hilo_mensaje CASCADE NOT NULL
  usuario_id       : UUID FK→user         CASCADE NOT NULL
  ultimo_leido_at  : TIMESTAMP nullable                    (NULL = nunca leyó)
  PRIMARY KEY (hilo_id, usuario_id)
}
```

### E-MSG-M — MensajeInterno

```
MensajeInterno {
  id           : UUID PK          gen_random_uuid()
  tenant_id    : UUID FK→tenant   CASCADE NOT NULL
  hilo_id      : UUID FK→hilo_mensaje CASCADE NOT NULL
  remitente_id : UUID nullable FK→user SET NULL            (NULL = mensaje del sistema)
  cuerpo       : TEXT NOT NULL
  created_at   : TIMESTAMP        DEFAULT now()
  deleted_at   : TIMESTAMP nullable
}
```

**Reglas del modelo**:
- Un hilo tiene al menos 2 participantes (iniciador + al menos 1 destinatario).
- Al crear el hilo, se insertan automáticamente los participantes en `HiloParticipante`.
- El iniciador se agrega como participante con `ultimo_leido_at = now()` (ya leyó el primer mensaje).
- Los destinatarios se agregan con `ultimo_leido_at = NULL` (no han leído).
- `HiloMensaje.updated_at` se actualiza en cada `INSERT` de `MensajeInterno` (trigger o service).
- Un usuario solo puede ver hilos donde aparece en `HiloParticipante`.
- Mensajes del sistema: `remitente_id = NULL` (ver D-C20-4).
- Soft delete de `HiloMensaje` → soft delete en cascada de sus `MensajeInterno` en la capa de service.

---

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/v1/inbox/hilos` | Lista de hilos del usuario (paginada) |
| `POST` | `/api/v1/inbox/hilos` | Crear hilo + primer mensaje |
| `GET` | `/api/v1/inbox/hilos/{hilo_id}` | Mensajes de un hilo |
| `POST` | `/api/v1/inbox/hilos/{hilo_id}/mensajes` | Responder en hilo |
| `PATCH` | `/api/v1/inbox/hilos/{hilo_id}/leer` | Marcar hilo como leído |

**Auth**: solo `get_current_user` (JWT válido). Sin permiso especial.
**Scope**: todos los endpoints filtran por `current_user.id` como participante.

---

## Schemas Pydantic

### `HiloCreate`
```python
class HiloCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    asunto: str
    destinatarios: list[UUID]   # al menos 1; todos deben pertenecer al mismo tenant
    cuerpo: str                 # cuerpo del primer mensaje
```

### `MensajeCreate`
```python
class MensajeCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cuerpo: str
```

### `MensajeResponse`
```python
class MensajeResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    hilo_id: UUID
    remitente_id: UUID | None   # None si es del sistema
    remitente_nombre: str | None
    cuerpo: str
    created_at: datetime
    # NUNCA se expone email_cifrado ni ningún campo PII del remitente
```

### `HiloResponse`
```python
class HiloResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    asunto: str
    iniciador_id: UUID
    iniciador_nombre: str
    participantes: list[UUID]
    no_leidos: int              # mensajes con created_at > ultimo_leido_at del current_user
    ultimo_mensaje_at: datetime  # = hilo_mensaje.updated_at
    created_at: datetime
```

### `HiloDetalle`
```python
class HiloDetalle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hilo: HiloResponse
    mensajes: list[MensajeResponse]
```

---

## `InboxService`

Archivo: `backend/app/services/inbox_service.py`

```
InboxService(
    session: AsyncSession,
    tenant_id: UUID,
    hilo_repo: HiloMensajeRepository,
    mensaje_repo: MensajeInternoRepository,
)

async listar_hilos(usuario_id: UUID, offset=0, limit=20) → list[HiloResponse]
    - JOIN HiloParticipante WHERE usuario_id = current_user.id
    - ORDER BY hilo_mensaje.updated_at DESC
    - no_leidos: COUNT(mensaje_interno WHERE created_at > hp.ultimo_leido_at)

async crear_hilo(iniciador_id: UUID, data: HiloCreate) → HiloResponse
    - Validar destinatarios en el mismo tenant
    - INSERT hilo_mensaje
    - INSERT hilo_participante (iniciador + destinatarios)
    - INSERT mensaje_interno (primer mensaje)
    - UPDATE hilo_participante.ultimo_leido_at = now() para el iniciador

async get_hilo(hilo_id: UUID, usuario_id: UUID) → HiloDetalle
    - Verificar que usuario_id ∈ participantes del hilo → sino 404
    - SELECT mensajes ORDER BY created_at ASC

async responder(hilo_id: UUID, remitente_id: UUID, data: MensajeCreate) → MensajeResponse
    - Verificar participante → sino 404
    - INSERT mensaje_interno
    - UPDATE hilo_mensaje.updated_at = now()

async marcar_leido(hilo_id: UUID, usuario_id: UUID) → None
    - UPDATE hilo_participante SET ultimo_leido_at = now()
      WHERE hilo_id = :hilo_id AND usuario_id = :usuario_id
```

---

## Repositorios

### `HiloMensajeRepository`

Archivo: `backend/app/repositories/hilo_mensaje_repository.py`

Extiende `BaseRepository[HiloMensaje]`.

```python
async list_for_user(usuario_id: UUID) → Sequence[...]:
    # SELECT hilo_mensaje JOIN hilo_participante
    # WHERE hilo_participante.usuario_id = usuario_id
    # AND hilo_mensaje.deleted_at IS NULL
    # ORDER BY updated_at DESC

async is_participante(hilo_id: UUID, usuario_id: UUID) → bool:
    # SELECT 1 FROM hilo_participante WHERE hilo_id=:id AND usuario_id=:uid
```

### `MensajeInternoRepository`

Archivo: `backend/app/repositories/mensaje_interno_repository.py`

Extiende `BaseRepository[MensajeInterno]`.

```python
async list_by_hilo(hilo_id: UUID) → Sequence[MensajeInterno]:
    # ORDER BY created_at ASC, WHERE deleted_at IS NULL
```

---

## Aislamiento y seguridad

- **Multi-tenant**: `HiloMensaje.tenant_id` y `MensajeInterno.tenant_id` siempre se fijan por repositorio.
- **PII nunca expuesta**: `MensajeResponse` incluye `remitente_id` (UUID) y `remitente_nombre` (nombre plaintext). Nunca `email_cifrado` ni otro campo cifrado.
- **Cross-user**: un usuario que intenta acceder a un hilo donde no es participante recibe 404 (no 403) para no revelar existencia del hilo.
- **Cross-tenant**: imposible por tenant_id en repositorio + FK cascade.

---

## Escenarios

### Crear hilo entre dos usuarios
```
DADO que el COORDINADOR (user-A) y el PROFESOR (user-B) están en el mismo tenant
CUANDO POST /api/v1/inbox/hilos con asunto="Consulta", destinatarios=[user-B.id], cuerpo="Hola"
ENTONCES 201 con HiloResponse
Y hilo_participante tiene rows para user-A y user-B
Y mensaje_interno tiene 1 fila con remitente_id=user-A.id
Y user-A.ultimo_leido_at = now() (ya leyó su propio mensaje)
Y user-B.ultimo_leido_at = NULL (no ha leído)
```

### Listar inbox
```
DADO que el PROFESOR (user-B) tiene 3 hilos: 2 no leídos, 1 leído
CUANDO GET /api/v1/inbox/hilos
ENTONCES lista de 3 HiloResponse en orden de updated_at DESC
Y los 2 no leídos tienen no_leidos > 0
Y el leído tiene no_leidos = 0
```

### Responder en hilo
```
DADO que el PROFESOR (user-B) es participante del hilo-1
CUANDO POST /api/v1/inbox/hilos/{hilo-1.id}/mensajes con cuerpo="Respuesta"
ENTONCES 201 con MensajeResponse
Y hilo_mensaje.updated_at se actualiza
Y user-A ve el hilo como no_leidos=1 (recibió la respuesta)
```

### Marcar como leído
```
DADO que el COORDINADOR (user-A) tiene no_leidos=1 en hilo-1
CUANDO PATCH /api/v1/inbox/hilos/{hilo-1.id}/leer
ENTONCES 200
Y hilo_participante.ultimo_leido_at = now() para user-A
Y GET /api/v1/inbox/hilos devuelve no_leidos=0 para hilo-1
```

### Acceso a hilo ajeno → 404
```
DADO que el PROFESOR (user-B) NO es participante del hilo-2
CUANDO GET /api/v1/inbox/hilos/{hilo-2.id}
ENTONCES 404 (no 403)
```

### Destinatario en otro tenant → 422
```
DADO que user-A es del TENANT-A y user-C es del TENANT-B
CUANDO user-A hace POST /api/v1/inbox/hilos con destinatarios=[user-C.id]
ENTONCES 422 "destinatario no pertenece al tenant"
```

### Inbox vacío
```
DADO que el ADMIN no tiene ningún hilo
CUANDO GET /api/v1/inbox/hilos
ENTONCES 200 con lista vacía []
```

### Aislamiento multi-tenant (inbox)
```
DADO que user-A del TENANT-A y user-X del TENANT-B tienen un hilo en TENANT-A
CUANDO user-X intenta GET /api/v1/inbox/hilos (autenticado en TENANT-B)
ENTONCES lista vacía (no ve hilos de otro tenant)
```
