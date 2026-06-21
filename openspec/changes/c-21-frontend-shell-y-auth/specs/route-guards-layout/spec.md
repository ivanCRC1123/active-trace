## ADDED Requirements

### Requirement: ProtectedRoute redirects unauthenticated users to login

`<ProtectedRoute>` SHALL wrap any route that requires authentication. If `sessionStore.accessToken` is null (no active session), it SHALL redirect to `/login`, preserving the originally requested path in location state (`{from: location.pathname}`) so login can redirect back after success.

#### Scenario: Unauthenticated access redirects to login
- **GIVEN** `sessionStore.accessToken === null`
- **WHEN** the user navigates to a protected route (e.g., `/dashboard`)
- **THEN** they are redirected to `/login`
- **AND** the original path `/dashboard` is stored in location state `{from: "/dashboard"}`

#### Scenario: Authenticated user accesses protected route
- **GIVEN** `sessionStore.accessToken === "valid.token"`
- **WHEN** the user navigates to a protected route
- **THEN** the route renders its children component normally

#### Scenario: After login, user is redirected to originally requested path
- **GIVEN** the user was redirected to `/login` from `/equipos`
- **WHEN** login completes successfully
- **THEN** the user is navigated to `/equipos` (from location state), not to the default `/dashboard`

---

### Requirement: ProtectedRoute blocks access for insufficient permissions

`<ProtectedRoute permission="modulo:accion">` SHALL additionally verify that the authenticated user has the specified permission. If the user is authenticated but lacks the permission, they SHALL see an "Acceso denegado" page (not a redirect to login), showing a clear message and a link back to the dashboard.

#### Scenario: User without required permission sees access denied
- **GIVEN** the user is authenticated with `roles: ["PROFESOR"]`
- **AND** the route requires `permission="liquidaciones:ver"` (which PROFESOR does not have)
- **WHEN** the user navigates to that route
- **THEN** an "Acceso denegado" component is rendered in place of the route content
- **AND** the user is NOT redirected to `/login`
- **AND** a "Volver al inicio" link is visible

#### Scenario: User with required permission accesses the route
- **GIVEN** the user is authenticated with `roles: ["FINANZAS"]`
- **AND** `usePermission("liquidaciones:ver")` returns `true` for FINANZAS
- **WHEN** the user navigates to the liquidaciones route
- **THEN** the route renders its children normally

#### Scenario: Route without permission prop requires only authentication
- **GIVEN** `<ProtectedRoute>` without a `permission` prop
- **AND** the user is authenticated (any role)
- **WHEN** the user navigates to that route
- **THEN** the route renders its children without checking permissions

---

### Requirement: usePermission hook resolves permission from session store

`usePermission(codigo: string): boolean` SHALL be a hook that reads the user's effective permissions from `sessionStore` and returns `true` if the user has the given permission code.

The source of permissions depends on OQ-C21-02:
- **Opción B** (preferred): permissions are loaded from `GET /api/auth/me/permissions` after login and stored in `sessionStore.permissions: Record<string, string>`.
- **Opción A** (fallback): permissions are derived from `sessionStore.user.roles` using a local matrix `shared/config/permissions.ts` that mirrors `core/permissions.py`.

The hook interface is identical regardless of the option chosen.

#### Scenario: User has permission — hook returns true
- **GIVEN** `sessionStore.permissions` contains `{"calificaciones:importar": "own"}`
- **WHEN** `usePermission("calificaciones:importar")` is called
- **THEN** it returns `true`

#### Scenario: User lacks permission — hook returns false
- **GIVEN** `sessionStore.permissions` does NOT contain `"liquidaciones:ver"`
- **WHEN** `usePermission("liquidaciones:ver")` is called
- **THEN** it returns `false`

#### Scenario: No session — hook returns false
- **GIVEN** `sessionStore.accessToken === null` (no session)
- **WHEN** `usePermission("cualquier:permiso")` is called
- **THEN** it returns `false`

---

### Requirement: AppShell renders navigation menu filtered by user permissions

`AppShell` SHALL render a sidebar/header navigation with menu items. Each item SHALL only appear if `usePermission(item.permission)` returns `true` for the current user. Items without a `permission` key are always visible to authenticated users.

Navigation items (minimum set for C-21; extended by C-22/23/24):

| Label | Route | Permission |
|-------|-------|------------|
| Dashboard | `/dashboard` | *(siempre visible)* |
| Mi perfil | `/perfil` | *(siempre visible)* |
| Calificaciones | `/calificaciones` | `calificaciones:importar` |
| Comunicaciones | `/comunicaciones` | `comunicacion:enviar` |
| Equipos docentes | `/equipos` | `equipos:asignar` |
| Auditoría | `/auditoria` | `auditoria:ver` |
| Liquidaciones | `/liquidaciones` | `liquidaciones:ver` |
| Admin | `/admin` | `estructura_academica:gestionar` |

#### Scenario: PROFESOR only sees their allowed items
- **GIVEN** a user with `roles: ["PROFESOR"]` who has `calificaciones:importar` and `comunicacion:enviar`
- **WHEN** `AppShell` renders the navigation
- **THEN** "Calificaciones" and "Comunicaciones" menu items are visible
- **AND** "Liquidaciones" and "Auditoría" are NOT visible

#### Scenario: ADMIN sees all items
- **GIVEN** a user with `roles: ["ADMIN"]`
- **WHEN** `AppShell` renders the navigation
- **THEN** all navigation items (including "Auditoría" and "Admin") are visible

#### Scenario: Dashboard and Mi perfil are always visible when authenticated
- **GIVEN** any authenticated user regardless of role
- **WHEN** `AppShell` renders
- **THEN** "Dashboard" and "Mi perfil" navigation items are visible

---

### Requirement: Logout button in AppShell clears session

`AppShell` SHALL include a logout button (or menu item) that triggers the logout flow: calls `authService.logout()`, then `sessionStore.logout()`, then navigates to `/login`.

#### Scenario: Logout button is visible in AppShell
- **GIVEN** an authenticated user
- **WHEN** `AppShell` renders
- **THEN** a logout button or link is visible

#### Scenario: Clicking logout redirects to login
- **GIVEN** the user is authenticated
- **WHEN** the user clicks the logout button
- **THEN** `sessionStore.getState().accessToken === null` after the action
- **AND** the user is on `/login`
