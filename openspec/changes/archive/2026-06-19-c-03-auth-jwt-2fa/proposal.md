## Why

activia-trace no tiene capa de autenticación. Sin un sistema de login, emisión de JWT, refresh con rotación, 2FA opcional, recuperación de contraseña y rate limiting, ningún usuario puede acceder al sistema de forma segura ni se puede establecer la identidad que requieren todos los changes posteriores (C-04 RBAC, C-05 audit log, C-06 estructura académica, etc.). Cada uno de esos changes —y toda operación del sistema— depende de que exista una sesión autenticada que proporcione `user_id`, `tenant_id` y `roles` de forma confiable.

## What Changes

- **POST /api/auth/login**: endpoint público que recibe `email` + `password`, valida contra Argon2id, verifica 2FA si está habilitado (TOTP), y emite un par access token (15min) + refresh token (7 días con rotación).
- **POST /api/auth/refresh**: endpoint público que recibe un refresh token válido, lo invalida (rotación), y emite un nuevo par. Si el refresh ya fue usado → se invalida toda la familia de tokens (family revocation).
- **POST /api/auth/logout**: endpoint autenticado que revoca la sesión activa (invalida el refresh token).
- **POST /api/auth/2fa/enroll**: endpoint autenticado que genera un secreto TOTP y lo devuelve como QR/URI para que el usuario lo configure en su app 2FA (Google Authenticator, Authy, etc.).
- **POST /api/auth/2fa/verify**: endpoint autenticado que valida un código TOTP contra el secreto almacenado. Si es válido, marca el 2FA como `enabled` para el usuario.
- **POST /api/auth/forgot**: endpoint público que recibe un email, genera un recovery token de un solo uso (expiración corta, ej. 15 min), y lo envía por email (el worker de email se integrará en cambios posteriores; inicialmente se loguea el token para desarrollo).
- **POST /api/auth/reset**: endpoint público que recibe un recovery token + nueva password, valida el token (no expirado, no usado) y actualiza el hash de la contraseña.
- **Rate limiting 5/60s por IP+email** en login: si se excede, el endpoint retorna 429 Too Many Requests.
- **Dependency `get_current_user`** en `core/dependencies.py`: resuelve identidad + tenant desde el JWT verificado y devuelve un objeto `CurrentUser` (user_id, tenant_id, roles, is_2fa_enabled). Esta dependencia es usada por todos los endpoints protegidos.
- **Modelos nuevos**: `User` (minimal: id, tenant_id, email, password_hash, nombre, apellido, is_2fa_enabled, totp_secret, timestamps, soft delete), `RefreshToken` (id, user_id, tenant_id, token_hash, family_id, expires_at, revoked_at, timestamps, soft delete), `RecoveryToken` (id, user_id, tenant_id, token_hash, expires_at, used_at, timestamps).
- **Migración Alembic 002**: crea tablas `user`, `refresh_token`, `recovery_token` + seed del ADMIN inicial para el tenant "TUPAD".
- **Tests**: login OK/KO (credenciales inválidas, email inexistente), refresh rotation (reuso invalida la familia), 2FA flow completo (enroll → verify → login gated), recovery token único (usado no puede reutilizarse), rate limit (5 intentos → bloqueo temporal), identidad inmutable por parámetro (enviar user_id en body no altera la sesión).

**No hay cambios BREAKING**: es el tercer change del proyecto; se agregan modelos, endpoints y lógica de seguridad sobre los cimientos de C-01 y C-02.

## Capabilities

### New Capabilities

- `auth-login`: Validación de credenciales (email + Argon2id), gated 2FA si está habilitado, emisión de par JWT (access 15min + refresh con rotación). Claims mínimos: `user_id`, `tenant_id`, `roles`, `exp`. Respeto estricto de la regla de oro: identidad exclusivamente del JWT verificado.
- `auth-refresh-logout`: Rotación de refresh token (el usado se invalida; reuso invalida la familia completa). Logout que revoca la sesión activa.
- `auth-2fa-totp`: 2FA opcional por usuario basado en TOTP (RFC 6238). Flujo: enroll (genera secreto + QR), verify (valida código y activa), login gated (entre password OK y emisión de sesión se exige TOTP).
- `auth-password-recovery`: Solicitud de recuperación con token de un solo uso por email (expiración corta). Reset de contraseña con validación del token.
- `auth-rate-limiting`: Rate limiting 5 intentos cada 60 segundos por combinación IP+email en el endpoint de login. Retorna 429 al exceder.
- `auth-get-current-user`: Dependencia FastAPI `get_current_user` que verifica el JWT (firma, expiración, tenant-scope) y devuelve un objeto `CurrentUser(user_id, tenant_id, roles)` que toda operación protegida usa como identidad del actor.

### Modified Capabilities

- *(Ninguna: es el tercer change del proyecto, no existen specs previos que modificar. La dependency `get_db` de C-01 no cambia su interfaz.)*

## Impact

- **Nuevos modelos**: `User`, `RefreshToken`, `RecoveryToken` en `app/models/`. `User` usa `BaseEntityMixin` de C-02. `RefreshToken` y `RecoveryToken` también son tenant-scoped.
- **Nuevas dependencias Python**: `pyotp` (generación/verificación TOTP), `python-jose[cryptography]` o `PyJWT` (JWT creación/verificación). Se agregan a `pyproject.toml`.
- **Nuevo código en `app/core/`**:
  - `core/security.py` → JWT create/verify helpers, Argon2id hash/verify (ocupa el reservado de C-01).
  - `core/dependencies.py` → se agrega `get_current_user`.
  - `core/auth/` (nuevo paquete) → servicios de autenticación, rate limiter, 2FA TOTP.
- **Nuevos schemas Pydantic** en `app/schemas/auth.py`: login request/response, refresh request/response, 2FA enroll/verify request/response, forgot/reset request/response.
- **Nuevos repositories**: `UserRepository`, `RefreshTokenRepository`, `RecoveryTokenRepository` en `app/repositories/`.
- **Nuevo service**: `AuthService` en `app/services/auth_service.py` con orquestación del flujo completo de autenticación.
- **Nuevos routers**: `app/api/v1/routers/auth.py` con endpoints públicos y protegidos de auth.
- **Migración Alembic 002**: crea tablas `user`, `refresh_token`, `recovery_token` con índices necesarios.
- **Seed de ADMIN inicial**: el tenant "TUPAD" (creado manualmente o vía seed) recibe un usuario ADMIN por defecto con email y contraseña configurables vía variables de entorno.
- **Nuevos tests**: `tests/test_auth_login.py`, `tests/test_auth_refresh.py`, `tests/test_auth_2fa.py`, `tests/test_auth_recovery.py`, `tests/test_auth_rate_limit.py`, `tests/test_get_current_user.py`.
- **Rate limiter storage**: usa un diccionario en memoria (para MVP/single-process) o Redis si está disponible. Inicialmente se implementa en memoria con `asyncio.Lock` para concurrencia.
- **Dependencias**: requiere C-01 (scaffold, database.py, config.py) y C-02 (BaseEntityMixin, BaseRepository, encryption, Tenant model, migración 001).
- **Habilita** a C-04 (RBAC: `require_permission` depende de `get_current_user`), C-05 (audit log necesita actor autenticado), y todos los changes de Fase 2+ que requieran sesión.
- **Governance**: CRITICO — autenticación, seguridad de contraseñas, 2FA, JWT, rate limiting. Errores aquí comprometen la seguridad de todo el sistema. Solo se entrega análisis y diseño; esperar confirmación antes de codificar.
