## Context

El backend tiene endpoints de auth completos (C-03: login, refresh, logout, 2FA, recovery; C-04: RBAC, `/api/auth/me`). El frontend parte de cero: no hay `frontend/` en el repositorio. Node v24.14.0 y npm 11.9.0 están disponibles.

El diseño del cliente HTTP y el almacenamiento de tokens son las decisiones más críticas de este change: definen el modelo de seguridad del frontend y condicionan cómo C-22/23/24 interactúan con el backend. Se surfacean cinco decisiones que requieren tu confirmación antes de implementar.

## Goals / Non-Goals

**Goals:**

- Scaffold Vite + React 18 + TypeScript con la estructura feature-based definida en `docs/ARQUITECTURA.md §4`.
- Cliente Axios centralizado en `shared/services/api.ts` con interceptor JWT + refresh transparente.
- Pantallas de login (email + password + tenant_code), 2FA challenge (TOTP), y recuperación de contraseña.
- Guard de rutas por permiso RBAC (`modulo:accion`), no solo por estado de autenticación.
- Session store reactivo con access token, refresh token, y permisos efectivos del usuario.
- Layout shell con menú filtrado por permisos.
- Tests con Vitest + Testing Library + MSW.
- Contenedor Docker (multi-stage build + nginx serve).

**Non-Goals:**

- Features de dominio (calificaciones, atrasados, equipos, etc.) → C-22/23/24.
- Enrollment 2FA desde perfil (configurar TOTP por primera vez) → C-22 o feature de perfil.
- Impersonación en frontend → change futuro.
- Portal del alumno → Fase 2 post-MVP.
- PWA / offline → fuera de scope.
- Internacionalización → fuera de scope.

---

## Decisions

### D1 — Almacenamiento de tokens: ¿dónde viven access token y refresh token?

**El problema**: el backend devuelve `{access_token, refresh_token}` en el body JSON. El frontend debe persistir ambos para no forzar re-login en cada recarga de página.

**Opciones:**

| Opción | Access token | Refresh token | XSS | CSRF | UX recarga |
|--------|-------------|---------------|-----|------|------------|
| A | memoria (variable JS) | `localStorage` | ✗ refresh expuesto | ✓ no hay cookie | ✓ sobrevive |
| B | memoria | memoria | ✓ | ✓ | ✗ pierde sesión al recargar |
| C | memoria | `sessionStorage` | ~ (limitado a tab) | ✓ | ~ (muere al cerrar tab) |
| D | memoria | httpOnly cookie (backend la setea) | ✓ | ✗ necesita CSRF token | ✓ sobrevive |

**Implicaciones de cada opción:**

- **Opción A (recomendada para el MVP sin cambios al backend)**: El access token vive en memoria (JS closure/Zustand), seguro contra XSS porque no es accesible desde `document.cookie` ni `localStorage`. El refresh token en `localStorage` es accesible para JS, pero el atacante necesita XSS para leerlo; si hay XSS, el juego ya está perdido de todas formas. Simple de implementar con el backend actual. Riesgo: si hay XSS, el refresh token puede ser robado y usado fuera de contexto. Mitigación: Content-Security-Policy estricto + sanitización de inputs.

- **Opción B (más segura, peor UX)**: Ambos tokens en memoria. El usuario debe hacer login de nuevo al recargar la página. Para una aplicación de gestión académica de uso intensivo durante el día, esto es inaceptable. Descartada.

- **Opción C (compromiso)**: Refresh en `sessionStorage` sobrevive recargas en la misma pestaña pero no cierre del navegador. Semánticamente correcto para "sesión de navegador". Viable pero menos conveniente que A para usuarios que trabajan en múltiples pestañas.

- **Opción D (más segura, requiere cambio al backend)**: El endpoint `/api/auth/login` y `/api/auth/refresh` setean el refresh token como `Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict; Secure`. El frontend nunca "ve" el refresh token. CSRF se mitiga con `SameSite=Strict`. Requiere modificar los endpoints de C-03 para setear la cookie en lugar de devolverla en JSON. Es la opción correcta a largo plazo.

**✅ RESUELTA — OQ-C21-01 cerrada:** Se eligió **Opción D** (httpOnly cookie). Los endpoints `/login`, `/refresh`, `/logout` y `/2fa/verify-login` de C-03 fueron modificados: el refresh token se setea como cookie `httpOnly; SameSite=Strict; Path=/api/auth; Secure=${COOKIE_SECURE}`. El frontend **nunca ve ni almacena el refresh token** — el store (Zustand) solo guarda el `access_token` y los `permissions`. La implementación y los tests de backend fueron actualizados en la sesión de prep C-21 (antes de arrancar el scaffold).

---

### D2 — Fuente de permisos para el guard de rutas

**El problema**: `GET /api/auth/me` devuelve `{user_id, tenant_id, roles: string[]}`. No devuelve permisos (`modulo:accion`). Los permisos se resuelven server-side en C-04 mediante `get_user_permissions()`. El frontend necesita saber si el usuario tiene permiso `X` para renderizar/redirigir antes de que el backend responda.

**Opciones:**

| Opción | Descripción | Pros | Contras |
|--------|-------------|------|---------|
| A | Frontend mantiene copia de la matriz rol→permiso como `const` TypeScript | No requiere cambio al backend | Riesgo de drift si la matriz cambia en backend |
| B | Backend agrega `GET /api/auth/me/permissions` que devuelve `{permisos: Record<string, string>}` | Fuente única de verdad | Requiere un endpoint nuevo (cambio al backend, pequeño) |
| C | Guard solo por rol (no por permiso fino) | Más simple | No refleja el modelo RBAC real del sistema |
| D | No guarda en frontend; solo reacciona al 403 del backend | Cero duplicación | Muy mala UX: el usuario ve el contenido y luego recibe error |

**Análisis:**

La matriz rol→permiso de C-04 está en `backend/app/core/permissions.py` (catálogo en base de datos, no hardcodeada). Si la Opción A duplica la matriz, hay que mantenerla sincronizada manualmente. En el MVP con roles y permisos estables, el drift es aceptable; en producción con cambios frecuentes de permisos, no lo es.

La Opción B agrega un endpoint muy simple: el router de auth ya tiene `get_current_user` y `get_user_permissions()` existe como función en `core/permissions.py`. Es un cambio de 15-20 líneas en el backend y es la opción correcta a largo plazo.

**✅ RESUELTA — OQ-C21-02 cerrada:** Se eligió **Opción B** (endpoint `/api/auth/me/permissions`). El endpoint fue implementado en C-03 como parte del prep de C-21: `GET /api/auth/me/permissions` devuelve `{permissions: Record<string, string>}` (código → scope). El frontend llama a este endpoint post-login y almacena el resultado en el store Zustand. `usePermission(codigo)` consulta el store directamente — no hay fallback a matriz local, no hay drift posible.

---

### D3 — State machine del login con 2FA

**El flujo de dos pasos de C-03:**
1. `POST /api/auth/login` → puede responder con `{access_token, refresh_token}` (sin 2FA) o `{requires_2fa: true, session_token: "..."}` (con 2FA).
2. Si `requires_2fa: true`, el usuario ingresa su código TOTP y se llama a `POST /api/auth/2fa/verify-login` con `{session_token, code}`.

**Modelado frontend:**

El estado del flujo de login es una máquina de tres estados:

```
IDLE
  │ usuario envía credenciales válidas
  ▼
AWAITING_CREDENTIALS_RESULT
  │                         │
  │ sin 2FA                 │ requires_2fa: true (+ session_token en estado)
  ▼                         ▼
AUTHENTICATED             AWAITING_2FA
                            │
                            │ usuario envía código TOTP válido
                            ▼
                          AUTHENTICATED
```

El `session_token` se guarda en el estado del componente `LoginPage` (no en el store global) durante el tiempo de vida de la pantalla de 2FA — dura máximo 5 minutos y es de un solo uso, sin valor fuera del flujo de login.

**Componentes:**
- `LoginPage`: orquesta la máquina de estados. Renderiza `CredentialsForm` o `TwoFAForm` según el estado.
- `CredentialsForm`: email + password + tenant_code. Submit → llama a `authService.login()`.
- `TwoFAForm`: input TOTP de 6 dígitos. Submit → llama a `authService.verify2FA(session_token, code)`.

El `session_token` pasa de `LoginPage` a `TwoFAForm` como prop; no se expone fuera del módulo `features/auth/`.

**Decisión tomada:** state machine en componente (`LoginPage`) con `useState<LoginStep>`. No se usa una librería de state machine (XState sería overkill para 3 estados). No hay `LOADING` global — cada formulario tiene su propio estado `isPending` del hook `useMutation`.

---

### D4 — Manejo de 401s concurrentes: refresh deduplicado

**El problema**: en una pantalla con múltiples queries (TanStack Query puede emitir 3-5 requests en paralelo al cargar), si el access token expiró, todos los requests fallan con 401 al mismo tiempo. Sin deduplicación, el interceptor haría N llamadas a `POST /api/auth/refresh`, lo cual es incorrecto: el servidor tiene rotación de refresh tokens, por lo que la segunda llamada encontraría el primer refresh token ya revocado y devolvería 401, deslogueando al usuario incorrectamente.

**Solución: promise compartida (mutex de refresh)**

```typescript
// En shared/services/api.ts
let refreshingPromise: Promise<TokenPair> | null = null;

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    // Caso 1: el 401 vino del propio endpoint de refresh → logout, no reintentar
    if (originalRequest.url?.includes('/api/auth/refresh')) {
      sessionStore.getState().logout();
      return Promise.reject(error);
    }

    // Caso 2: el 401 vino de otro endpoint → refrescar (con deduplicación)
    if (!refreshingPromise) {
      refreshingPromise = doRefresh()
        .catch((err) => {
          sessionStore.getState().logout();
          return Promise.reject(err);
        })
        .finally(() => {
          refreshingPromise = null;
        });
    }

    try {
      const tokens = await refreshingPromise;
      originalRequest.headers['Authorization'] = `Bearer ${tokens.access_token}`;
      return axiosInstance(originalRequest);
    } catch {
      return Promise.reject(error);
    }
  }
);
```

**Por qué esto funciona:** el primer request que detecta 401 crea `refreshingPromise`. Los siguientes requests que también detectan 401 (mientras el refresh está en vuelo) esperan la misma promesa en lugar de emitir su propia llamada. Cuando el refresh completa, todos los requests en espera reintentan con el nuevo access token.

**Decisión tomada:** promise compartida con módulo-level variable. No requiere librería externa.

---

### D5 — Prevención de loop infinito en el interceptor

**El riesgo**: si `POST /api/auth/refresh` devuelve 401 (refresh token expirado, revocado, o familia revocada), el interceptor podría reintentar indefinidamente.

**Solución**: el interceptor verifica si el request fallido apunta al endpoint de refresh antes de intentar refrescar (ver Caso 1 en D4). Si el 401 viene de `/api/auth/refresh`, se llama directamente a `logout()` y se rechaza la promesa sin reintentar.

Adicionalmente, se marca el request original con un flag `_retried: true` antes de reintentarlo, y el interceptor no reintenta si `_retried` ya está en `true`. Esto previene loops en casos edge donde el nuevo access token también da 401 inmediatamente (e.g., cuenta desactivada entre el refresh y el retry).

```typescript
if (originalRequest._retried) {
  sessionStore.getState().logout();
  return Promise.reject(error);
}
originalRequest._retried = true;
```

**Decisión tomada:** flag `_retried` + verificación de URL de refresh. Sin esta defensa, un 401 persistente en cualquier endpoint post-refresh causaría un loop.

---

### D6 — Estructura de carpetas

La estructura sigue exactamente `docs/ARQUITECTURA.md §4`:

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
└── src/
    ├── main.tsx                   # Bootstrap: QueryClient, Router, StoreProvider
    ├── App.tsx                    # Rutas raíz con React Router
    ├── router.tsx                 # Definición de rutas con lazy-loading
    ├── store/
    │   └── sessionStore.ts        # Zustand: {accessToken, refreshToken, user, permissions}
    ├── features/
    │   └── auth/
    │       ├── components/
    │       │   ├── CredentialsForm.tsx    # Formulario email + password + tenant_code
    │       │   └── TwoFAForm.tsx          # Formulario código TOTP
    │       ├── hooks/
    │       │   └── useLogin.ts            # useMutation wrapper
    │       ├── services/
    │       │   └── authService.ts         # login(), verify2FA(), logout(), forgotPassword(), resetPassword(), getMe()
    │       ├── types/
    │       │   └── auth.types.ts          # LoginRequest, LoginResponse, TwoFARequiredResponse, etc.
    │       └── pages/
    │           ├── LoginPage.tsx          # Orquesta CredentialsForm / TwoFAForm
    │           ├── ForgotPasswordPage.tsx
    │           └── ResetPasswordPage.tsx
    └── shared/
        ├── services/
        │   └── api.ts             # Axios instance + interceptor JWT/refresh
        ├── components/
        │   ├── ProtectedRoute.tsx # Guard: verifica sesión + permiso
        │   └── AppShell.tsx       # Layout: header + nav + outlet
        └── hooks/
            └── usePermission.ts   # hasPermission(codigo) desde sessionStore
```

**Reglas:**
- Componentes < 200 LOC. Si crece, extraer sub-componentes.
- `features/auth/` no importa desde otra feature. Las features son aisladas.
- `shared/` puede ser importado por cualquier feature.
- No hay `any`. No hay class components.
- Tailwind classes en el JSX; no hay archivos CSS separados salvo `index.css` (reset + Tailwind base).

---

## Risks / Trade-offs

- **[Opción A de token storage]** Si se elige localStorage para el refresh token, un XSS permite robar el refresh token. Mitigación: CSP estricto, no usar `dangerouslySetInnerHTML`, sanitizar toda entrada de usuario antes de renderizar.

- **[Drift de la matriz permisos si se usa Opción A de D2]** Si los permisos en backend cambian y no se actualiza `shared/config/permissions.ts`, los guards client-side serán incorrectos. El backend sigue siendo la última línea de defensa (retorna 403), pero el UX será roto (usuario ve pantalla y luego recibe error). Mitigación: agregar el endpoint `/api/auth/me/permissions` lo antes posible.

- **[Estado de 2FA `session_token` en componente]** El `session_token` tiene vida de 5 minutos. Si el usuario tarda más de 5 minutos en ingresar el TOTP (navegó a otro tab, etc.), la siguiente llamada a `verify-login` fallará con 401. El componente debe detectar ese error y redirigir al inicio del flujo (volver a mostrar `CredentialsForm`) con un mensaje "El código de sesión expiró, volvé a ingresar tus credenciales".

- **[TanStack Query y refresh transparente]** TanStack Query tiene su propio mecanismo de retry. Si el interceptor de Axios ya está manejando el retry tras refresh, el retry de TanStack Query es redundante y puede causar doble request. Mitigación: configurar `retry: false` en el `QueryClient` global (o al menos en las queries de auth).

## Open Questions

**OQ-C21-01 — Token storage (D1)**: ¿Opción A (refresh en localStorage, sin cambio al backend) u Opción D (refresh en httpOnly cookie, requiere modificar C-03)?

**OQ-C21-02 — Permisos en frontend (D2)**: ¿Opción A (matriz local en `shared/config/permissions.ts`) u Opción B (nuevo endpoint `GET /api/auth/me/permissions` en el backend)?

**OQ-C21-03 — Librería de estado global**: El diseño usa Zustand para el session store. ¿Preferís Context + useReducer (sin dependencia extra) o Zustand (API más ergonómica para stores pequeños)? Zustand es la recomendación por ser más sencillo de testear.

**OQ-C21-04 — React Router**: ¿Versión 6 (actual) o v7 (Data Router)? El diseño usa v6 con `<Routes>` y `<Route>`. Si preferís migrar a la API de v7 (loaders, actions), el cambio es en `router.tsx` y es aislado.

**OQ-C21-05 — Tenant code en login**: C-03 requiere `tenant_code` explícito en el formulario de login. ¿Querés que el campo sea visible siempre, o lo ocultamos con un default desde variable de entorno (`VITE_DEFAULT_TENANT_CODE`) para el MVP con un solo tenant?
