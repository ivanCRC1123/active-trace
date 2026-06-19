## Context

activia-trace no tiene autenticación. C-01 creó el scaffold FastAPI con engine asíncrono y `get_db`. C-02 agregó `BaseEntityMixin`, `BaseRepository` con tenant isolation, modelo `Tenant`, y utilidad AES-256. Ahora necesitamos la capa de identidad: login con email + password (Argon2id), JWT access (15 min) + refresh con rotación, 2FA TOTP opcional, recuperación de contraseña, rate limiting, y la dependency `get_current_user` que todos los endpoints protegidos usarán.

La regla de oro (identidad/tenant exclusivamente del JWT verificado) es el pilar de seguridad de todo el sistema. Cada endpoint que requiera autenticación usará `get_current_user`. Los claims del JWT son mínimos: `user_id`, `tenant_id`, `roles`, `exp`. Los permisos finos se resuelven server-side en C-04.

## Goals / Non-Goals

**Goals:**

- **POST /api/auth/login**: validación de credenciales (email + Argon2id), gate de 2FA TOTP si el usuario lo tiene habilitado, emisión de JWT access (15 min) + refresh token con rotación (7 días). Claims mínimos en access token: `user_id`, `tenant_id`, `roles`, `exp`. Refresh token incluye `family_id` para detección de reuso.
- **POST /api/auth/refresh**: recibe refresh token válido, lo invalida, emite nuevo par (access + refresh). Si el refresh token recibido ya fue usado → se invalida **toda la familia** (todos los refresh tokens con el mismo `family_id`). Esto evita ataques de robo de refresh token.
- **POST /api/auth/logout**: endpoint protegido que revoca el refresh token de la sesión actual.
- **POST /api/auth/2fa/enroll**: endpoint protegido que genera un secreto TOTP (RFC 6238), lo devuelve como URI `otpauth://` + QR code (como string o URL para que el frontend lo renderice), pero no activa 2FA hasta verify.
- **POST /api/auth/2fa/verify**: endpoint protegido que recibe un código TOTP de 6 dígitos, lo valida contra el secreto almacenado. Si es válido, marca `is_2fa_enabled = True` en el usuario.
- **POST /api/auth/forgot**: endpoint público que recibe email, verifica que exista un usuario con ese email, genera un `RecoveryToken` único (hash del token, expiración 15 min) y lo emite en la respuesta (en producción se enviaría por email; para MVP se retorna en respuesta para testing).
- **POST /api/auth/reset**: endpoint público que recibe token + nueva password, valida el token (no expirado, no usado), actualiza el hash de la contraseña, invalida el token, y revoca todas las sesiones activas del usuario.
- **Rate limiting**: máximo 5 intentos de login cada 60 segundos por combinación IP+email. Implementación en memoria con `asyncio.Lock` y diccionario `dict[str, list[float]]` (IP+email → timestamps). Retorna 429 con header `Retry-After`.
- **Dependency `get_current_user`**: extrae el token del header `Authorization: Bearer <token>`, verifica firma y expiración, decodifica claims, y retorna un objeto `CurrentUser(user_id: UUID, tenant_id: UUID, roles: list[str])`. Este objeto es inyectado en toda operación protegida.
- **Modelos**: `User` (minimal), `RefreshToken` (con family_id), `RecoveryToken`. Todos heredan de `BaseEntityMixin` de C-02.
- **Migración Alembic 002**: tabla `user`, `refresh_token`, `recovery_token` + seed de usuario ADMIN inicial para tenant "TUPAD".
- **Tests con base de datos real**: login OK/KO, refresh rotation (reuso invalida familia), 2FA flow (enroll → verify → login gated), recovery token único, rate limit, identidad inmutable por parámetro.

**Non-Goals:**

- Permisos finos RBAC (`require_permission`) → C-04.
- Audit log de acciones de autenticación → C-05.
- Modelo de usuario completo (perfil, legajo, roles asignados, etc.) → C-07.
- Integración con Moodle SSO → Fase 2 (post-MVP, ADR-001).
- Envío real de emails en forgot/reset → se integra con worker de comunicaciones en cambios posteriores; en MVP se retorna el token en la respuesta.
- Almacenamiento de rate limiting en Redis → se implementa en memoria; migración a Redis cuando haya múltiples workers/instancias.
- Interfaz de usuario (frontend) de login → C-21 (frontend shell y auth).
- Impersonación → cambio futuro (ADR-004).
- CSRF protection → se implementa en frontend (cookie SameSite) y no en backend API REST.

## Decisions

### D1 — JWT: algoritmo HS256 con `SECRET_KEY` desde settings

Se usa **HS256** (HMAC with SHA-256) con la `SECRET_KEY` de configuración (mín. 32 caracteres, validada en C-01). El access token se firma con esta clave; el refresh token también (aunque no es un JWT estándar — ver D3).

**Alternativa descartada**: RS256 (RSA key pair). Se descarta porque introduce complejidad de gestión de claves (par público/privado, rotación) sin beneficio real para un MVP monorepo con un solo servicio firmante. HS256 es suficiente mientras el servicio que firma y verifica sea el mismo. Si en el futuro se necesita verificación por servicios externos, se migra a RS256.

El módulo `core/security.py` expone:

```python
def create_access_token(user_id: UUID, tenant_id: UUID, roles: list[str]) -> str: ...
def verify_access_token(token: str) -> dict: ...
```

### D2 — Identificación de tenant por `tenant_code` explícito en login

La identificación del tenant durante el login se realiza mediante un campo `tenant_code` explícito en el body del request `POST /api/auth/login`. 

```json
{
  "tenant_code": "tupad",
  "email": "admin@tupad.edu.ar",
  "password": "********"
}
```

**Flujo de login:**

1. El sistema recibe `tenant_code`, `email`, `password`.
2. Busca el tenant por `Tenant.code` (columna única, slug corto como `"tupad"`, `"unr"`).
3. Si el tenant no existe → HTTP 401 `"Invalid credentials"` (mismo mensaje genérico que credenciales incorrectas).
4. Si el tenant existe → busca el usuario por `email` dentro de ese `tenant_id`.
5. Valida la contraseña contra el hash Argon2id almacenado.
6. Si todo es válido → emite JWT access token con `tenant_id` del tenant resuelto.

**Justificación:**
- **Simplifica el MVP**: no requiere DNS wildcard ni configuración de subdominios.
- **Desacoplado**: la API recibe `tenant_code` como parámetro explícito; en el futuro se puede migrar a resolución automática por subdominio sin cambiar la lógica interna (solo se agrega un middleware que extrae el tenant del subdominio y lo pasa como `tenant_code` al service de login).
- **Aislamiento desde el primer paso**: nunca se busca un usuario sin saber primero a qué tenant pertenece.

**Variante futura (no implementar ahora):** cuando se implemente frontend (C-21), se puede pedir primero el tenant_code en una pantalla inicial y luego mostrar el formulario de login. O detectar el tenant por subdominio y ocultar el campo por completo.

**SQL injection / validación:** el `tenant_code` se usa exclusivamente para buscar el tenant en DB vía parámetro parametrizado (SQLAlchemy ORM). No se concatena en strings SQL.

### D3 — Refresh token: opaque token con hash en DB (no JWT)

El refresh token es un **string aleatorio opaco** de 32 bytes generado con `secrets.token_urlsafe(32)` (no un JWT). Se almacena su hash SHA-256 en la tabla `refresh_token` junto con `family_id`, `user_id`, `tenant_id`, `expires_at`, `revoked_at`.

Razones:
- El refresh token se emite con vida larga (7 días) y necesita ser revocable individualmente (logout) o por familia (reuso). Un JWT no puede ser revocado sin un blocklist.
- Almacenar el hash permite detectar reuso: si alguien presenta un refresh token ya usado (revocado), se invalida toda la familia (todos los tokens con el mismo `family_id`).
- El `family_id` es un UUID generado en la primera emisión; todos los refresh tokens de una misma sesión (incluyendo refrescos) comparten el mismo `family_id`.

**Alternativa descartada**: refresh token como JWT con claims. Se descarta porque la revocación requeriría un blocklist, lo que agrega complejidad y estado que un refresh opaco con hash ya resuelve.

```python
# Generación
raw_token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

# Verificación
stored = await refresh_token_repo.get_by_hash(token_hash)
if stored and stored.revoked_at:
    await refresh_token_repo.revoke_family(stored.family_id)  # reuso!
    raise HTTPException(401)
```

### D4 — Rotación con family revocation (token reuse detection)

El flujo de refresh rotation implementa detección de reuso (token reuse detection):

1. Cliente presenta refresh token A.
2. Servidor busca por hash en DB → lo encuentra, no revocado → emite nuevo par (access + refresh B).
3. Servidor **revoca A** (setea `revoked_at`).
4. Si el atacante tenía A y lo presenta después de que B fue emitido → servidor encuentra A como revocado → **revoca toda la familia** (todos los refresh tokens con `family_id` = family_of_A, incluyendo B).
5. El usuario legítimo, al intentar usar B y encontrar que su sesión fue revocada, debe hacer login nuevamente.

Este patrón es el recomendado por OAuth 2.0 BCP (Best Current Practice) y Auth0 para refresh token rotation con detección de robo.

```python
async def refresh(self, raw_token: str) -> TokenPair:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    stored = await self.refresh_token_repo.get_by_hash(token_hash)
    if not stored:
        raise InvalidToken()
    if stored.revoked_at:
        # Token reuse detected → revoke entire family
        await self.refresh_token_repo.revoke_family(stored.family_id)
        raise TokenReused()
    # Revoke current, emit new pair
    await self.refresh_token_repo.revoke(stored.id)
    return await self._emit_pair(stored.user_id, stored.tenant_id, stored.family_id)
```

### D5 — 2FA TOTP (RFC 6238) con `pyotp`

2FA es opcional por usuario. Se implementa con la librería `pyotp`:

- **Enroll**: genera un secreto TOTP de 16 bytes (base32), lo almacena en `user.totp_secret` (cifrado con AES-256, igual que PII sensible), y devuelve una URI `otpauth://totp/activia-trace:{email}?secret={secret}&issuer=activia-trace`.
- **Verify**: recibe código de 6 dígitos, lo valida con `pyotp.TOTP(secret).verify(code)` con ventana de 1 paso adelante/atrás (30s cada paso).
- **Login gated**: cuando `user.is_2fa_enabled = True`, el login retorna `{"requires_2fa": true, "session_token": "<opaque>"}`. El frontend debe pedir el código TOTP y llamar a `POST /api/auth/2fa/verify-login` con el código + session_token. Si es válido, se emite el par JWT. Si no, error 401.

El `session_token` es un token opaco de un solo uso (similar a refresh token) que dura 5 minutos, solo válido para completar el 2FA después de password OK. Se almacena en DB con hash.

```python
# Login con 2FA
user = await user_repo.get_by_email(email)
if not verify_argon2(password, user.password_hash):
    raise InvalidCredentials()
if user.is_2fa_enabled:
    session_token = await self._create_2fa_session_token(user)
    return {"requires_2fa": True, "session_token": session_token}
return await self._emit_pair(user.id, user.tenant_id)

# Verify 2FA login
stored = await twofa_session_repo.get_by_hash(session_token_hash)
if not stored or stored.revoked_at or stored.expires_at < now:
    raise InvalidSession()
await twofa_session_repo.revoke(stored.id)
return await self._emit_pair(stored.user_id, stored.tenant_id)
```

**Alternativa descartada**: devolver un access token parcial (sin permisos) que se complete tras 2FA. Se descarta porque un token parcial podría ser usado para acceder a recursos sin 2FA completo. El session_token opaco es más seguro: solo es canjeable por un par completo en el endpoint de verify-login.

### D6 — Modelo `User` minimal (para C-03; se expande en C-07)

El modelo `User` en C-03 es minimalista: solo lo necesario para auth. Se expandirá en C-07 con perfil, legajo, roles, etc.

```python
class User(Base, BaseEntityMixin):
    __tablename__ = "user"
    
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Cifrado AES-256
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

Notas:
- `email` es único a nivel global (no solo por tenant) para simplicidad en login. Si en el futuro dos tenants necesitan el mismo email, se agrega unique constraint compuesto `(tenant_id, email)`.
- `totp_secret` se cifra con AES-256 antes de almacenar (usa `core/encryption.py` de C-02).
- `password_hash` se genera con Argon2id (ver D7).

### D7 — Argon2id vía `passlib[argon2]` o `argon2-cffi`

Se usa **Argon2id** (recomendación OWASP para hash de contraseñas). La implementación usa `passlib.hash.argon2` con el wrapper `argon2-cffi`:

```python
from passlib.hash import argon2

def hash_password(password: str) -> str:
    return argon2.using(time=2, memory=102400, parallelism=8).hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return argon2.verify(password, password_hash)
```

Parámetros: time_cost=2, memory_cost=102400 (100MB), parallelism=8. Son valores conservatives que proveen seguridad adecuada con rendimiento aceptable para un MVP.

**Alternativa descartada**: bcrypt. Argon2id es el ganador del PHC (Password Hashing Competition) y es recomendado por OWASP como primera opción. Python tiene bindings maduros (`argon2-cffi`). bcrypt sería la segunda mejor opción, pero Argon2id es superior contra ataques de GPU/ASIC.

### D8 — Rate limiting en memoria con sliding window

Implementación en memoria usando un diccionario:

```python
class InMemoryRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self._store: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
    
    async def check(self, key: str) -> bool:
        # key = f"{ip}:{email}"
        async with self._lock:
            now = time.time()
            timestamps = self._store.get(key, [])
            # Remove old entries outside window
            timestamps = [t for t in timestamps if now - t < self.window_seconds]
            if len(timestamps) >= self.max_attempts:
                return False  # Rate limited
            timestamps.append(now)
            self._store[key] = timestamps
            return True
```

El rate limiter se inyecta como singleton en el service de autenticación. En producción con múltiples workers, se migraría a Redis.

### D9 — `get_current_user` como FastAPI dependency con inyección de tenant

```python
async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = verify_access_token(token)
    except (JWTError, ExpiredSignatureError) as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    user_id = UUID(payload["sub"])
    tenant_id = UUID(payload["tenant_id"])
    roles = payload.get("roles", [])
    
    # Verify user still exists and is active
    user_repo = UserRepository(db, tenant_id)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or deleted")
    
    return CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
    )
```

**CurrentUser** es un Pydantic model (no ORM) que se pasa como dependencia:

```python
class CurrentUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    tenant_id: UUID
    roles: list[str]
```

**Regla de oro (inmutable)**: `CurrentUser` se deriva exclusivamente del JWT verificado. Nunca se sobreescribe con datos del body/query/headers. Si un endpoint necesita verificar que un `user_id` del body coincida con el de la sesión, se compara explícitamente como validación de negocio.

### D10 — Seed del ADMIN inicial

La migración 002 incluye un seed (via `op.execute` o en un script separado `scripts/seed_dev.py`) que:

1. Crea un usuario ADMIN para el tenant "TUPAD" (buscando el tenant por código).
2. Email y contraseña del ADMIN se configuran vía variables de entorno `SEED_ADMIN_EMAIL` y `SEED_ADMIN_PASSWORD` (con defaults seguros para desarrollo).
3. El usuario se crea con `is_active=True`, sin 2FA.

### D11 — RefreshToken y RecoveryToken models

```python
class RefreshToken(Base, BaseEntityMixin):
    __tablename__ = "refresh_token"
    
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    family_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

class RecoveryToken(Base, TimeStampedMixin, SoftDeleteMixin):
    __tablename__ = "recovery_token"
    # NOTA: No hereda TenantScopedMixin porque forgot no requiere sesión.
    # Sin embargo, incluimos tenant_id para relacionarlo con el tenant del usuario.
    
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
```

`RecoveryToken` no hereda `BaseEntityMixin` completo porque forgot/reset son endpoints públicos sin sesión; pero mantenemos `tenant_id` para aislamiento y trazabilidad.

## Risks / Trade-offs

- **[Rate limiter en memoria no persiste entre reinicios]** → Mitigación: aceptable para MVP. Si el servidor se reinicia, los contadores se pierden, pero es un riesgo menor frente a la simplicidad. Se migrará a Redis en C-?? cuando se implemente multi-worker.
- **[Detección de reuso de refresh token revoca toda la familia]** → Esto puede causar logout forzado al usuario legítimo si el atacante robó un refresh token y lo usó antes que el legítimo. Mitigación: es el comportamiento deseado según OAuth 2.0 BCP. El usuario legítimo recibe un error de token revocado y debe hacer login nuevamente, momento en el que se inicia una nueva familia.
- **[2FA session token opaco de 5 min puede ser interceptado]** → Mitigación: el session_token se envía en response body, no en URL. Solo es canjeable en 5 minutos. HTTPS obligatorio (TLS 1.3, RNF-07). El endpoint verify-login también tiene rate limiting para prevenir brute force del TOTP.
- **[Dependencia `pyotp` nueva]** → Mitigación: `pyotp` es una librería madura, liviana y sin dependencias externas (solo stdlib). No introduce riesgo de mantenimiento.
- **[Dependencia `argon2-cffi` nueva]** → Mitigación: `argon2-cffi` tiene bindings C, wheels para todas las plataformas, y es mantenido por Hynek Schlawack (mismo mantenedor de `python-jose`). Es la librería Argon2 más usada en Python.
- **[Seed de ADMIN con contraseña en variable de entorno puede filtrarse en logs]** → Mitigación: la variable `SEED_ADMIN_PASSWORD` no se loguea nunca. Sólo se usa una vez en el seed. En producción, el admin debe cambiar la contraseña en el primer login (política de cambio obligatorio en primera sesión, que se implementa como feature adicional).
- **[Regla de oro: que el JWT contenga roles puede quedar desactualizado si cambian los roles en DB]** → Mitigación: los roles en el JWT son un snapshot del momento del login/refresh. Si un rol cambia o se revoca, el usuario debe hacer login nuevamente (el access token expira en 15 min, el refresh puede durar hasta 7 días). Para permisos finos (C-04), se resuelven server-side en cada request, no desde el JWT. Este riesgo está acotado a la vista de roles (no permisos) y es aceptable para el MVP. En futuras iteraciones se puede implementar verificación de roles en DB en cada request si es necesario.

## Migration Plan

No hay migración de datos (es la primera vez que se crean estos modelos). Deploy:

1. Ejecutar `alembic upgrade head` (migración 002 ejecutada después de 001 de C-02). Crea tablas `user`, `refresh_token`, `recovery_token`.
2. Ejecutar script `scripts/seed_admin.py` (o incluir seed en la migración) que:
   - Busca el tenant "TUPAD" por código.
   - Crea usuario ADMIN con email y password de variables de entorno.
   - Loggea éxito sin mostrar la contraseña.
3. Rollback: `alembic downgrade -1` revierte la migración 002 (dropea las 3 tablas).

## Open Questions

- **Email delivery for forgot/reset**: para el MVP, el token de recovery se retorna en el body de la respuesta (no se envía email real). ¿Es aceptable o necesitamos mockeable el envío desde ahora? Decisión: en C-03 se retorna el token en la respuesta. La integración con el worker de comunicaciones se hará en cambios posteriores.
- **¿Refresh token duración exacta?**: 7 días parece razonable para el MVP. ¿Debe ser configurable por tenant? Por ahora se configura vía variable de entorno `REFRESH_TOKEN_EXPIRE_DAYS` (default 7).
- **¿Rate limit debe diferenciar por tenant?**: inicialmente es global (IP+email). Si un atacante ataca múltiples tenants desde la misma IP, el rate limit aplica igual. Esto es correcto. ¿Necesitamos un rate limit adicional por tenant? Se deja como mejora futura.
- **¿El seed de ADMIN se incluye en la migración Alembic o en un script separado?**: Script separado (`scripts/seed_admin.py`) para no mezclar schema con datos. La migración 002 solo crea tablas.
- **¿2FA recovery codes?**: TOTP no tiene recovery codes por defecto. Se podrían generar códigos de backup (como Google Authenticator) pero se deja para una iteración futura.
