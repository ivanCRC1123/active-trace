## ADDED Requirements

### Requirement: Centralized Axios client attaches JWT to every request

The module `shared/services/api.ts` SHALL export a single Axios instance (`api`). A request interceptor SHALL read the `accessToken` from `sessionStore` and attach `Authorization: Bearer <token>` to every outgoing request. Requests to public endpoints (login, refresh, forgot, reset) SHALL still send the header if a token exists — the backend ignores it on public routes.

#### Scenario: Authenticated request includes Authorization header
- **GIVEN** `sessionStore` has `accessToken = "valid.jwt.token"`
- **WHEN** any component calls `api.get('/api/something')`
- **THEN** the outgoing request includes `Authorization: Bearer valid.jwt.token`

#### Scenario: Unauthenticated request omits Authorization header
- **GIVEN** `sessionStore` has `accessToken = null`
- **WHEN** any component calls `api.post('/api/auth/login', body)`
- **THEN** the outgoing request does NOT include an `Authorization` header

---

### Requirement: Interceptor refreshes token transparently on 401 and retries the original request

When a response with status 401 is received for a non-refresh endpoint, the interceptor SHALL call `POST /api/auth/refresh` with the stored refresh token, update the session store with the new token pair, and retry the original request with the new access token. The original caller SHALL receive the successful response as if no 401 had occurred.

#### Scenario: 401 triggers transparent refresh and retry
- **GIVEN** `sessionStore` has a valid refresh token but an expired access token
- **WHEN** a component calls `api.get('/api/materias')` and the server returns 401
- **THEN** the interceptor calls `POST /api/auth/refresh` once
- **AND** the interceptor retries `GET /api/materias` with the new access token
- **AND** the component receives the successful response from the retry

#### Scenario: Retried request is marked to prevent re-intercept
- **GIVEN** a request that received 401 and was retried after refresh
- **WHEN** the retried request also returns 401 (e.g., account deactivated mid-session)
- **THEN** the interceptor detects `_retried: true` on the request config
- **AND** calls `sessionStore.logout()` without retrying again
- **AND** rejects the promise with the 401 error

---

### Requirement: Concurrent 401s deduplicate into a single refresh call

When multiple requests fail with 401 simultaneously (e.g., parallel TanStack Query fetches on page load), the interceptor SHALL issue exactly one call to `POST /api/auth/refresh`. All pending requests SHALL await the same refresh promise and retry with the new token once it resolves.

#### Scenario: Three concurrent 401s result in one refresh call
- **GIVEN** three requests (`/api/a`, `/api/b`, `/api/c`) all return 401 simultaneously
- **WHEN** all three error interceptors fire within the same event loop tick
- **THEN** `POST /api/auth/refresh` is called exactly once (not three times)
- **AND** all three original requests are retried with the new access token
- **AND** all three callers receive their successful responses

#### Scenario: Refresh promise is cleared after completion
- **GIVEN** a refresh cycle completed successfully
- **WHEN** a new 401 occurs in a later request (e.g., token expired again after 15 min)
- **THEN** the interceptor initiates a new refresh call (the shared promise was cleared)

---

### Requirement: 401 on the refresh endpoint itself triggers logout without retry

If `POST /api/auth/refresh` returns 401 (refresh token expired, revoked, or family revoked), the interceptor SHALL NOT attempt another refresh. It SHALL call `sessionStore.logout()` to clear all tokens and redirect the user to the login page.

#### Scenario: Refresh endpoint returns 401 → logout
- **GIVEN** `sessionStore` has a revoked refresh token
- **WHEN** the interceptor calls `POST /api/auth/refresh` and receives 401
- **THEN** `sessionStore.logout()` is called
- **AND** no further refresh attempts are made
- **AND** the original pending requests are rejected

#### Scenario: Refresh endpoint returns 401 does not cause infinite loop
- **GIVEN** the interceptor is handling a 401 from `POST /api/auth/refresh`
- **WHEN** the logout handler is called
- **THEN** no additional calls to `POST /api/auth/refresh` are made
- **AND** the interceptor terminates the error chain

---

### Requirement: 403 responses are passed through without refresh

A 403 Forbidden response means the user IS authenticated but lacks the required permission. The interceptor SHALL NOT attempt a refresh on 403. The error SHALL propagate to the caller so TanStack Query can surface it and the UI can show an access-denied state.

#### Scenario: 403 is not intercepted
- **GIVEN** a request returns 403 Forbidden
- **WHEN** the response interceptor fires
- **THEN** `POST /api/auth/refresh` is NOT called
- **AND** the 403 error is passed through to the query/mutation caller

---

### Requirement: Session store persists access token in memory and refresh token per design decision D1

The `sessionStore` (Zustand) SHALL store `accessToken: string | null` in memory (not persisted). The refresh token SHALL be stored per the resolution of OQ-C21-01 (D1 in design.md). The store SHALL expose: `setTokens(tokens: TokenPair): void`, `logout(): void`, `accessToken: string | null`, `refreshToken: string | null`.

#### Scenario: setTokens updates both tokens
- **GIVEN** `sessionStore` is initialized with null tokens
- **WHEN** `sessionStore.getState().setTokens({access_token: "a", refresh_token: "r"})`
- **THEN** `sessionStore.getState().accessToken === "a"`
- **AND** `sessionStore.getState().refreshToken === "r"`

#### Scenario: logout clears all session state
- **GIVEN** `sessionStore` has tokens and user info
- **WHEN** `sessionStore.getState().logout()`
- **THEN** `accessToken === null`, `refreshToken === null`, `user === null`, `permissions === []`
