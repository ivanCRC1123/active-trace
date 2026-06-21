## ADDED Requirements

### Requirement: Login page renders email, password, and tenant code fields

`LoginPage` SHALL render a form with three fields: `email` (input type email), `password` (input type password), and `tenant_code` (input type text). All fields are required. The form SHALL be validated with Zod before submission. A "Iniciar sesión" submit button triggers the login flow.

> Note: If OQ-C21-05 resolves to hiding the tenant_code field via env var `VITE_DEFAULT_TENANT_CODE`, the field is replaced by a hidden input pre-filled with the env var. The validation schema and service call remain unchanged.

#### Scenario: Renders login form with all required fields
- **WHEN** `LoginPage` is rendered
- **THEN** the document contains an input for email, an input for password, and an input or hidden field for tenant_code
- **AND** a submit button with text "Iniciar sesión" is visible

#### Scenario: Empty submission shows validation errors
- **WHEN** the user clicks "Iniciar sesión" without filling any field
- **THEN** Zod validation reports errors for email, password, and tenant_code
- **AND** the form does NOT call `authService.login()`

#### Scenario: Invalid email format shows validation error
- **WHEN** the user enters "not-an-email" in the email field and submits
- **THEN** a validation error "Email inválido" is displayed near the email field

---

### Requirement: Successful login without 2FA stores tokens and redirects to dashboard

When `POST /api/auth/login` returns `{access_token, refresh_token, token_type, expires_in}`, the login hook SHALL call `sessionStore.setTokens()`, then call `GET /api/auth/me` to populate the user profile and permissions in the store, and finally navigate to `/dashboard`.

#### Scenario: Successful login navigates to dashboard
- **GIVEN** MSW handler returns `{access_token: "...", refresh_token: "...", token_type: "bearer", expires_in: 900}`
- **WHEN** the user fills valid credentials and submits the form
- **THEN** `sessionStore.accessToken` is set to the returned access token
- **AND** the user is navigated to `/dashboard`
- **AND** the login form is no longer visible

#### Scenario: Invalid credentials shows error message
- **GIVEN** MSW handler returns 401 `{"detail": "Invalid credentials"}`
- **WHEN** the user fills credentials and submits the form
- **THEN** an error message "Credenciales inválidas" is displayed
- **AND** the user remains on the login page
- **AND** the password field is cleared

#### Scenario: Rate limit error shows retry message
- **GIVEN** MSW handler returns 429 with `Retry-After: 30` header
- **WHEN** the user submits the form
- **THEN** an error message "Demasiados intentos. Intentá de nuevo en 30 segundos." is displayed

---

### Requirement: Login with 2FA transitions to TOTP input step

When `POST /api/auth/login` returns `{requires_2fa: true, session_token: "..."}`, `LoginPage` SHALL transition from `CredentialsForm` to `TwoFAForm`. The `session_token` SHALL be kept in `LoginPage` state (not in the global store). The user SHALL see a field to enter their 6-digit TOTP code.

#### Scenario: 2FA response transitions to TOTP form
- **GIVEN** MSW handler returns `{requires_2fa: true, session_token: "sess_abc123"}`
- **WHEN** the user fills valid credentials and submits the form
- **THEN** the credentials form is replaced by a TOTP input form
- **AND** the TOTP form shows an input for a 6-digit code
- **AND** the session_token is held in component state (NOT in sessionStore, NOT in localStorage)

#### Scenario: Credentials form is not visible during 2FA step
- **GIVEN** the login flow is in the AWAITING_2FA state
- **WHEN** the component renders
- **THEN** the email, password, and tenant_code fields are NOT in the document

---

### Requirement: 2FA form submits session_token + code to complete login

When the user enters a 6-digit code in `TwoFAForm` and submits, the hook SHALL call `POST /api/auth/2fa/verify-login` with `{session_token, code}`. On success (200 with token pair), it stores tokens and navigates to dashboard. On 401 with invalid code, it shows an error. On 401 with expired session_token, it resets to the credentials form with an explanatory message.

#### Scenario: Valid TOTP code completes login
- **GIVEN** the flow is in AWAITING_2FA with a valid session_token
- **AND** MSW handler for `POST /api/auth/2fa/verify-login` returns a token pair
- **WHEN** the user enters a valid 6-digit code and submits
- **THEN** `sessionStore.setTokens()` is called with the returned tokens
- **AND** the user is navigated to `/dashboard`

#### Scenario: Invalid TOTP code shows error without resetting to credentials
- **GIVEN** the flow is in AWAITING_2FA
- **AND** MSW handler returns 401 `{"detail": "Invalid TOTP code"}`
- **WHEN** the user enters an invalid code and submits
- **THEN** an error message "Código inválido. Verificá tu aplicación de autenticación." appears
- **AND** the TOTP form remains visible (user can retry)
- **AND** the credentials form is still NOT visible

#### Scenario: Expired session_token resets to credentials form
- **GIVEN** the flow is in AWAITING_2FA
- **AND** MSW handler returns 401 `{"detail": "Invalid or expired session token"}`
- **WHEN** the user submits the TOTP form
- **THEN** `LoginPage` transitions back to the IDLE state (credentials form)
- **AND** a message "Tu sesión de verificación expiró. Volvé a ingresar tus credenciales." is shown

#### Scenario: Back link from 2FA step returns to credentials
- **GIVEN** the flow is in AWAITING_2FA
- **WHEN** the user clicks "Volver" or "Cancelar"
- **THEN** `LoginPage` transitions back to the IDLE state
- **AND** the credentials form is visible again

---

### Requirement: After successful login, GET /api/auth/me populates session store with user data

After setting tokens, the login hook SHALL call `GET /api/auth/me` (using the new access token) and store the returned `{user_id, tenant_id, roles}` in the session store. If the resolution of OQ-C21-02 includes a `/me/permissions` endpoint, permissions are also fetched and stored.

#### Scenario: /me response populates user in store
- **GIVEN** `GET /api/auth/me` returns `{user_id: "uuid-1", tenant_id: "t-uuid", roles: ["PROFESOR"]}`
- **WHEN** login completes successfully
- **THEN** `sessionStore.getState().user.roles` contains `["PROFESOR"]`
- **AND** `sessionStore.getState().user.user_id` equals `"uuid-1"`

---

### Requirement: Logout button revokes refresh token and clears session

A logout action SHALL call `POST /api/auth/logout` with the current refresh token, then call `sessionStore.logout()` (clears all tokens and user data), then navigate to `/login`. If the backend call fails (network error, 401), the client-side logout STILL proceeds.

#### Scenario: Logout clears session regardless of backend response
- **GIVEN** the user is authenticated
- **WHEN** the user triggers logout (even if `POST /api/auth/logout` fails)
- **THEN** `sessionStore.getState().accessToken === null`
- **AND** the user is navigated to `/login`
- **AND** the previous tokens are no longer in memory
