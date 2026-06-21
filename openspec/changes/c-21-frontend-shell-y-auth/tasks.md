## Pre-condición: resolver OQs de design.md antes de arrancar

- [ ] P.1 Rodrigo confirma D1 (OQ-C21-01): ¿refresh token en localStorage (Opción A) o httpOnly cookie (Opción D)?
- [ ] P.2 Rodrigo confirma D2 (OQ-C21-02): ¿matriz local en frontend (Opción A) o nuevo endpoint backend `/api/auth/me/permissions` (Opción B)?
- [ ] P.3 Rodrigo confirma OQ-C21-05: ¿tenant_code visible en el formulario o default desde `VITE_DEFAULT_TENANT_CODE`?

> Si se elige Opción D (httpOnly cookie), agregar una tarea 0.x para modificar los endpoints de C-03 antes de arrancar el scaffold.

---

## 1. Scaffold del proyecto (`frontend/`)

- [ ] 1.1 Crear `frontend/` con `npm create vite@latest . -- --template react-ts`
- [ ] 1.2 Instalar dependencias de producción: `react-router-dom@6`, `@tanstack/react-query@5`, `react-hook-form`, `zod`, `@hookform/resolvers`, `axios`, `zustand`, `tailwindcss`, `@tailwindcss/vite`
- [ ] 1.3 Instalar dependencias de desarrollo: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `msw`, `jsdom`, `@types/react`, `@types/react-dom`
- [ ] 1.4 Configurar `tailwind.config.ts` con content glob `./src/**/*.{ts,tsx}`
- [ ] 1.5 Configurar `vite.config.ts` con alias `@/ → src/` y plugin Vitest con entorno `jsdom`
- [ ] 1.6 Configurar `tsconfig.json` con strict mode, path aliases `@/*`
- [ ] 1.7 Crear estructura de carpetas: `src/features/auth/`, `src/shared/`, `src/store/`
- [ ] 1.8 Crear `Dockerfile` multi-stage (Node build → nginx serve)
- [ ] 1.9 Agregar servicio `frontend` al `docker-compose.yml` raíz
- [ ] 1.10 Verificar que `npm run build` y `npm test` pasan sin error

---

## 2. Session store (`src/store/sessionStore.ts`)

- [ ] 2.1 (RED) Escribir `src/store/sessionStore.test.ts`: setTokens popula tokens, logout limpia todo el estado, valores iniciales son null
- [ ] 2.2 (GREEN) Implementar `sessionStore` con Zustand: `accessToken`, `refreshToken`, `user`, `permissions`, `setTokens()`, `setUser()`, `setPermissions()`, `logout()`
- [ ] 2.3 (TRIANGULATE) Agregar tests para persistencia según decisión D1 (localStorage vs memoria)

---

## 3. Cliente HTTP centralizado (`src/shared/services/api.ts`)

- [ ] 3.1 (RED) Escribir `src/shared/services/api.test.ts` con MSW:
  - Test: request adjunta `Authorization: Bearer` cuando hay accessToken en store
  - Test: 401 en endpoint normal → refresh → retry con nuevo token
  - Test: tres 401 concurrentes → un solo refresh
  - Test: 401 en `/api/auth/refresh` → logout, sin retry
  - Test: request marcado `_retried` → logout, sin segundo retry
  - Test: 403 se pasa al caller sin intentar refresh
- [ ] 3.2 (GREEN) Implementar `api.ts`: instancia Axios con `baseURL` desde `import.meta.env.VITE_API_URL`, request interceptor (adjunta JWT), response interceptor (401 handling con promise compartida, flag `_retried`, loop prevention)
- [ ] 3.3 (TRIANGULATE) Agregar tests de edge cases: refresh exitoso seguido de otro 401 quince minutos después

---

## 4. Auth service (`src/features/auth/services/authService.ts`)

- [ ] 4.1 (RED) Escribir `src/features/auth/services/authService.test.ts`:
  - Test: `login()` con credenciales → retorna token pair
  - Test: `login()` con 2FA → retorna `{requires_2fa: true, session_token}`
  - Test: `verify2FA()` → retorna token pair
  - Test: `logout()` → llama al backend y retorna
  - Test: `forgotPassword()` → retorna siempre 200
  - Test: `resetPassword()` → retorna confirmación o lanza error
  - Test: `getMe()` → retorna `CurrentUser`
- [ ] 4.2 (GREEN) Implementar `authService.ts` con funciones `login()`, `verify2FA()`, `logout()`, `forgotPassword()`, `resetPassword()`, `getMe()`
- [ ] 4.3 Definir tipos en `src/features/auth/types/auth.types.ts`: `LoginRequest`, `LoginResponse`, `TwoFARequiredResponse`, `TokenPair`, `CurrentUser`, `ForgotRequest`, `ResetRequest`

---

## 5. Login page y componentes (`src/features/auth/`)

- [ ] 5.1 (RED) Escribir `src/features/auth/pages/LoginPage.test.tsx`:
  - Test: renderiza campos email, password, tenant_code y botón submit
  - Test: submit sin datos → errores de validación, no llama al service
  - Test: email inválido → error de validación
  - Test: credenciales inválidas (401) → mensaje de error, formulario visible
  - Test: login exitoso sin 2FA → tokens en store, navega a dashboard
  - Test: login con 2FA → transiciona a formulario TOTP
  - Test: TOTP inválido → mensaje de error, TOTP form visible
  - Test: TOTP con session_token expirado → vuelve a credentials form con mensaje
  - Test: TOTP válido → tokens en store, navega a dashboard
  - Test: botón "Volver" en TOTP → vuelve a credentials form
- [ ] 5.2 (GREEN) Implementar `LoginPage.tsx` con state machine (IDLE | AWAITING_2FA)
- [ ] 5.3 (GREEN) Implementar `CredentialsForm.tsx` con React Hook Form + Zod
- [ ] 5.4 (GREEN) Implementar `TwoFAForm.tsx` con React Hook Form + Zod (campo de 6 dígitos numéricos)
- [ ] 5.5 (GREEN) Implementar `useLogin.ts` hook (useMutation wrapper sobre authService)
- [ ] 5.6 (TRIANGULATE) Test de rate limit: 429 → mensaje con countdown

---

## 6. Recovery pages

- [ ] 6.1 (RED) Escribir `src/features/auth/pages/ForgotPasswordPage.test.tsx`:
  - Test: renderiza campo email y botón submit
  - Test: submit sin email → error de validación
  - Test: submit exitoso → mensaje de confirmación (no revela si email existe)
  - Test: MVP token display si backend retorna `recovery_token`
- [ ] 6.2 (GREEN) Implementar `ForgotPasswordPage.tsx`
- [ ] 6.3 (RED) Escribir `src/features/auth/pages/ResetPasswordPage.test.tsx`:
  - Test: lee token de URL param `?token=`
  - Test: passwords no coinciden → error de validación
  - Test: password < 8 chars → error de validación
  - Test: reset exitoso → navega a login con mensaje de éxito
  - Test: token inválido/expirado → mensaje de error + link a forgot
- [ ] 6.4 (GREEN) Implementar `ResetPasswordPage.tsx`

---

## 7. Route guards (`src/shared/components/ProtectedRoute.tsx`)

- [ ] 7.1 (RED) Escribir `src/shared/components/ProtectedRoute.test.tsx`:
  - Test: sin sesión → redirige a /login con `{from}` en location state
  - Test: con sesión → renderiza children
  - Test: con sesión pero sin permiso requerido → renderiza "Acceso denegado"
  - Test: con sesión y permiso correcto → renderiza children
  - Test: sin prop `permission` → solo verifica autenticación
  - Test: post-login con `{from}` en state → navega a la ruta original
- [ ] 7.2 (GREEN) Implementar `ProtectedRoute.tsx`
- [ ] 7.3 (RED) Escribir `src/shared/hooks/usePermission.test.ts`:
  - Test: permiso en store → retorna true
  - Test: permiso ausente en store → retorna false
  - Test: sin sesión → retorna false
- [ ] 7.4 (GREEN) Implementar `usePermission.ts`

---

## 8. App shell y layout (`src/shared/components/AppShell.tsx`)

- [ ] 8.1 (RED) Escribir `src/shared/components/AppShell.test.tsx`:
  - Test: PROFESOR → ve Calificaciones y Comunicaciones, no Liquidaciones ni Auditoría
  - Test: ADMIN → ve todos los items
  - Test: Dashboard y Mi perfil siempre visibles si autenticado
  - Test: botón logout visible
  - Test: click en logout → sessionStore limpio, navega a /login
- [ ] 8.2 (GREEN) Implementar `AppShell.tsx` con sidebar, header, outlet, y menú filtrado por `usePermission`
- [ ] 8.3 Crear `src/router.tsx` con lazy-loading de rutas: `/login`, `/forgot-password`, `/reset-password`, y rutas protegidas bajo `AppShell`
- [ ] 8.4 Crear `src/App.tsx` con `RouterProvider`
- [ ] 8.5 Crear placeholder `DashboardPage.tsx` (solo título "Dashboard") para que la navegación post-login funcione

---

## 9. Bootstrap y wiring

- [ ] 9.1 Configurar `src/main.tsx`: `QueryClientProvider` (con `retry: false`), `RouterProvider`, Zustand store provider si es necesario
- [ ] 9.2 Crear `src/index.css` con `@tailwind base; @tailwind components; @tailwind utilities;`
- [ ] 9.3 Agregar `VITE_API_URL` a `.env.development` y `.env.example`
- [ ] 9.4 Agregar `VITE_DEFAULT_TENANT_CODE` a variables de entorno (según resolución de OQ-C21-05)

---

## 10. Integración y verificación final

- [ ] 10.1 Levantar backend (`docker-compose up backend`) y frontend (`npm run dev`) en paralelo
- [ ] 10.2 Verificar flujo completo: login → dashboard → logout → redirecta a login
- [ ] 10.3 Verificar flujo 2FA: login con usuario 2FA habilitado → TOTP form → dashboard
- [ ] 10.4 Verificar refresh transparente: expirar access token manualmente → cualquier request lo refresca sin re-login
- [ ] 10.5 Verificar guard de permisos: navegar a ruta sin permiso → "Acceso denegado"
- [ ] 10.6 Verificar menú adaptativo: usuario PROFESOR vs ADMIN ven items distintos
- [ ] 10.7 Correr `npm test` → suite completa pasa (0 failed)
- [ ] 10.8 Correr `npm run typecheck` → 0 errores TypeScript
- [ ] 10.9 Verificar que ningún componente supera 200 LOC (`wc -l` o herramienta similar)

---

## 11. Cierre

- [ ] 11.1 Marcar `C-21` como `[x]` completo en `CHANGES.md`
- [ ] 11.2 Archivar openspec: `openspec/changes/c-21-frontend-shell-y-auth/` → `openspec/changes/archive/YYYY-MM-DD-c-21-frontend-shell-y-auth/`
