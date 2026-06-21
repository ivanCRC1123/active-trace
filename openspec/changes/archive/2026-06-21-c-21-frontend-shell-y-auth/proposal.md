## Why

El backend de autenticación (C-03), los permisos RBAC (C-04) y los módulos de dominio (C-05 a C-20) están implementados pero son inaccesibles para el usuario final: no hay interfaz. C-21 es la capa de presentación base de la que dependen todas las features de frontend (C-22, C-23, C-24). Sin este shell, no hay forma de iniciar sesión, navegar por la aplicación ni proteger rutas por permiso.

Además, el cliente HTTP centralizado con refresh transparente es infraestructura transversal: cada request de C-22/23/24 pasa por él. Si esta pieza no se diseña bien ahora, se paga la deuda en cada feature posterior.

## What Changes

- **Scaffold React 18 + TypeScript + Vite**: proyecto frontend desde cero en `frontend/`, con Tailwind CSS, TanStack Query, React Hook Form + Zod, Axios. Estructura feature-based (`features/{dominio}/{components,hooks,services,types,pages}`).
- **Cliente HTTP centralizado** (`shared/services/api.ts`): instancia Axios con interceptor que adjunta `Authorization: Bearer <access_token>` en cada request, detecta 401, refresca el token transparentemente, y reintenta el request original. Maneja 401s concurrentes con una sola llamada a refresh (no N). Detecta 401 en el propio refresh para evitar loop infinito → logout.
- **Pantalla de login**: formulario email + password + tenant_code validado con Zod. Flujo de 2FA: si el backend devuelve `requires_2fa: true`, el componente transiciona a un segundo paso donde se ingresa el código TOTP.
- **Pantalla de recuperación de contraseña**: formulario para solicitar recovery token (forgot) y para establecer nueva contraseña con token (reset).
- **Guard de rutas por permiso**: `<ProtectedRoute permission="modulo:accion" />` que redirige a login si no hay sesión y a una pantalla de acceso denegado si la sesión existe pero no tiene el permiso requerido.
- **Session store**: estado de sesión global (access token, refresh token, usuario/roles resueltos) con acceso reactivo desde cualquier componente.
- **Layout shell** con barra de navegación adaptada a los permisos de la sesión activa. El menú muestra solo los ítems accesibles para el rol del usuario.
- **Logout**: invalida el token en backend (`POST /api/auth/logout`), limpia el estado local, redirige a login.
- **Tests**: render de pantalla de login, flujo de auth completo (mock del service), guard redirige sin sesión, refresh transparente (interceptor), 2FA state machine.

**No hay cambios BREAKING al backend.** C-21 consume endpoints existentes de C-03 y C-04; no modifica schemas ni modelos.

## Capabilities

### New Capabilities

- `frontend-scaffold`: Vite + React 18 + TypeScript + Tailwind + TanStack Query + React Hook Form/Zod + Axios. Estructura feature-based. Proyecto standalone en `frontend/`, dockerizable.
- `http-client-centralizado`: Cliente Axios con interceptor JWT, refresh transparente con deduplicación de 401s concurrentes (promise compartida), y loop-infinite prevention (401 en refresh → logout directo).
- `auth-login`: Pantalla de login (email + password + tenant_code). Maneja la variante `requires_2fa: true` transicionando a un formulario TOTP en el mismo flujo. Valida con Zod, gestiona errores de credenciales/rate-limit.
- `auth-2fa-step`: Segundo paso del login para usuarios con 2FA habilitado. Envía `session_token + code` a `POST /api/auth/2fa/verify-login` y obtiene el par de tokens.
- `auth-recovery`: Pantallas Olvidé mi contraseña (solicita recovery token) y Restablecer contraseña (usa el token para setear nueva clave).
- `route-guard-permiso`: `<ProtectedRoute>` que protege rutas por permiso RBAC (`modulo:accion`), no solo por estado de autenticación.
- `session-store`: Store reactivo (Zustand o Context) con el par access/refresh token, roles del usuario, y utilidad `hasPermission(codigo)`.
- `app-shell-layout`: Layout base con header, barra lateral de navegación con ítems filtrados por permiso, y outlet para el contenido.
- `logout`: Flujo de cierre de sesión (revoca refresh en backend, limpia store, redirige a login).

### Modified Capabilities

- *(Ninguna: es el primer change de frontend. No existen caps frontend anteriores.)*

## Impact

- **Nuevo directorio `frontend/`**: proyecto Vite standalone. `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tailwind.config.ts`, `frontend/index.html`, `frontend/src/`.
- **Nuevas dependencias npm**: `react@18`, `react-dom`, `react-router-dom@6`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `axios`, `tailwindcss`, `zustand` (o Context), `typescript`, `vite`, `@vitejs/plugin-react`. Dev: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `msw` (Mock Service Worker para tests de integración).
- **Archivos nuevos en `frontend/src/`**:
  - `shared/services/api.ts` — cliente Axios + interceptor
  - `shared/hooks/usePermission.ts` — utilidad de verificación de permiso
  - `shared/components/ProtectedRoute.tsx` — guard por permiso
  - `shared/components/AppShell.tsx` — layout base
  - `features/auth/` — todo el módulo de auth (pages, components, hooks, services, types)
  - `store/sessionStore.ts` — estado global de sesión
  - `App.tsx`, `main.tsx`, `router.tsx`
- **Contenedor Docker frontend**: `frontend/Dockerfile` (multi-stage: build con Node, serve con nginx). Se agrega al `docker-compose.yml` raíz.
- **Dependencias**: consume C-03 (`POST /api/auth/login`, `/refresh`, `/logout`, `/2fa/verify-login`, `/forgot`, `/reset`) y C-04 (`GET /api/auth/me` para resolver roles/permisos de la sesión).
- **Habilita**: C-22 (features docente), C-23 (features coordinación), C-24 (features finanzas/admin). Todo frontend posterior importa `shared/services/api.ts` y usa `<ProtectedRoute>`.
- **Governance**: BAJO — pantallas y scaffold frontend sin lógica de negocio crítica. Autonomía total si pasan los tests.
