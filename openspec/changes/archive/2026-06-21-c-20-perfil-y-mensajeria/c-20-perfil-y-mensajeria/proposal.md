# C-20 — perfil-y-mensajeria-interna: Proposal

## Why

Con C-07 (usuarios) y C-03 (auth) como base, los usuarios del sistema pueden autenticarse pero
no pueden gestionar su propio perfil ni comunicarse entre sí dentro de la plataforma.

C-20 cierra dos brechas funcionales complementarias:

1. **Perfil propio (F11.1)**: todo usuario autenticado puede actualizar sus datos personales,
   fiscales y bancarios sin depender del ADMIN. Esto es crítico para que los datos de liquidación
   (CBU, alias, banco) sean mantenidos por el propio docente, reduciendo la carga administrativa
   del ADMIN y los errores de re-ingreso.

2. **Mensajería interna (F3.4, F11.2, FL-10)**: la plataforma necesita un canal de comunicación
   1:1 y 1:N entre usuarios registrados, distinto de los emails a alumnos (E21, C-12) y de los
   avisos broadcast (E13, C-15). Sin este canal, la coordinación no puede enviar instrucciones
   personalizadas a docentes específicos dentro del sistema.

3. **Logout (F11.3)**: el cierre de sesión explícito ya existe en C-03. C-20 lo documenta como
   capacidad del perfil de usuario, sin código nuevo.

## What Changes

### Sección A — Perfil propio

**Migración 015**: agrega columna `sexo VARCHAR(50) nullable` a tabla `user` (ver design D-C20-1).

**Endpoints nuevos** en `/api/v1/perfil`:
- `GET /api/v1/perfil` — devuelve el perfil del usuario autenticado (datos de E4, incluyendo email decifrado)
- `PATCH /api/v1/perfil` — actualiza campos editables; rechaza modificación de `cuil`

**Campos editables por el propio usuario**:
| Campo | Tipo | Cifrado | Notas |
|-------|------|---------|-------|
| `nombre` | str | no | |
| `apellidos` | str | no | |
| `email` | str | AES-GCM + HMAC | Actualiza `email_cifrado` + `email_hash` atómicamente; valida unicidad en tenant |
| `sexo` | str nullable | no | Valores libres (sin enum rígido) |
| `dni` | str nullable | AES-GCM | Re-cifrado transparente vía EncryptedString |
| `cbu` | str nullable | AES-GCM | Datos bancarios para liquidaciones |
| `alias_cbu` | str nullable | AES-GCM | |
| `banco` | str nullable | no | |
| `regional` | str nullable | no | |
| `legajo_profesional` | str nullable | no | Matrícula/registro profesional |
| `facturador` | bool | no | Modalidad de cobro: factura / liquidación |

**Campos de solo lectura** (rechazados por el endpoint de perfil):
- `cuil` — identificador fiscal principal (solo ADMIN puede modificarlo vía C-07)
- `legajo` — atributo institucional asignado por ADMIN

**Auditoría**: `PERFIL_EDITAR` nuevo en `audit_codes.py`, con `detalle.campos_modificados` listando
qué campos cambió el usuario en cada PATCH.

### Sección B — Mensajería interna

**Migración 015** (misma migración que sección A): crea tablas `hilo_mensaje`, `hilo_participante`,
`mensaje_interno`.

**Modelos nuevos**:
- `HiloMensaje` (E-MSG-H): cabecera del hilo con asunto, iniciador, timestamps
- `HiloParticipante`: join table usuario × hilo con `ultimo_leido_at` para tracking unread
- `MensajeInterno` (E-MSG-M): cuerpo del mensaje dentro del hilo; `remitente_id = NULL` para mensajes del sistema

**Endpoints nuevos** en `/api/v1/inbox`:
- `GET /api/v1/inbox/hilos` — lista de hilos del usuario autenticado (con conteo de no leídos)
- `POST /api/v1/inbox/hilos` — crear nuevo hilo + primer mensaje (especificando destinatarios)
- `GET /api/v1/inbox/hilos/{hilo_id}` — mensajes del hilo (requiere ser participante)
- `POST /api/v1/inbox/hilos/{hilo_id}/mensajes` — responder en hilo
- `PATCH /api/v1/inbox/hilos/{hilo_id}/leer` — marcar hilo como leído (actualiza `ultimo_leido_at`)

**Sin permiso nuevo**: acceso solo requiere JWT válido (self-scoped por `current_user.id`).

### Sección C — Logout

`POST /api/v1/auth/logout` ya existe en C-03 y revoca el refresh token.
C-20 no agrega código nuevo; solo referencia este endpoint en la documentación del perfil.

## New Capabilities

- `perfil:ver-propio` — cualquier autenticado puede ver su perfil
- `perfil:editar-propio` — cualquier autenticado puede editar sus datos propios
- `inbox:leer-propio` — cualquier autenticado puede leer su propia bandeja
- `inbox:enviar` — cualquier autenticado puede iniciar un hilo o responder
- `sesion:cerrar` — reusa C-03 logout (ya existente)

## Impact

| Capa | Archivos | Cambio |
|------|----------|--------|
| Models | `user.py` (sexo), `hilo_mensaje.py` (new), `hilo_participante.py` (new), `mensaje_interno.py` (new) | 1 modify + 3 new |
| Migration | `[rev]_015_perfil_mensajeria.py` | +1 |
| Repositories | `hilo_mensaje_repository.py` (new), `mensaje_interno_repository.py` (new) | +2 |
| Schemas | `perfil.py` (new), `inbox.py` (new) | +2 |
| Services | `perfil_service.py` (new), `inbox_service.py` (new) | +2 |
| Routers | `perfil.py` (new), `inbox.py` (new) | +2 |
| Audit codes | `audit_codes.py` (add PERFIL_EDITAR) | 1 modify |
| main.py | register 2 new routers | 1 modify |
| Tests | `test_perfil.py` (new), `test_inbox.py` (new) | +2 (~35 tests) |

## Dependencies

- **C-07** (usuarios): tabla `user` con PII cifrada, `email_cifrado`+`email_hash`, `EncryptedString` TypeDecorator, `hmac_email()`
- **C-05** (audit): `AuditService.log()` y `VALID_ACTION_CODES`
- **C-03** (auth): `get_current_user` dependency, logout reutilizado

C-20 **no desbloquea** changes críticos del camino principal (es leaf en el árbol de dependencias).

## Governance

**BAJO** para mensajería y vista de perfil; **MEDIO** para la actualización de email (requiere
atualización atómica cifrado + blind index). Ninguna operación requiere aprobación previa — pero
el design de email update debe revisarse contra D-C20-2 antes de implementar.
