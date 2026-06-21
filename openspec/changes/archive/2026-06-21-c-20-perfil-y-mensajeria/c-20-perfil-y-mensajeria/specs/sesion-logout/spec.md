# Spec: Cierre de sesión (F11.3)

## Alcance

F11.3 — "el usuario termina su sesión de forma explícita. El sistema invalida la sesión activa
y redirige al flujo de autenticación."

**No hay código nuevo en C-20.** El endpoint ya existe desde C-03.

---

## Endpoint existente

```
POST /api/v1/auth/logout
```

Implementado en `backend/app/api/v1/routers/auth.py`.

**Comportamiento**:
1. Recibe `refresh_token` en el body (opcional; si no se envía, es no-op).
2. Busca el refresh token en DB y lo revoca (`revoked_at = now()`).
3. Devuelve `200 OK` — el frontend descarta el access token y redirige al login.

**Auth**: el endpoint acepta un JWT válido vía `get_current_user` (el access token identifica al usuario), y adicionalmente el `refresh_token` a revocar.

---

## Por qué no hay código nuevo

- La lógica de revocación (C-03) ya invalida la sesión completa.
- El access token expira naturalmente (15 min) — no hay lista de revocación de access tokens.
- El frontend simplemente descarta el access token del storage local al recibir el 200.

---

## Referencia

- Implementación: `backend/app/core/auth/service.py` → `AuthService.logout()`
- Tests existentes: `backend/tests/test_auth.py` → `TestLogout`

C-20 puede referenciar este endpoint en la documentación de la Épica 11 sin implementar nada nuevo.
