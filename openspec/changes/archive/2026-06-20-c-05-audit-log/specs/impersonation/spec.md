## ADDED Requirements

### Requirement: JWT carries optional impersonado_id claim; CurrentUser exposes it

The system SHALL support access tokens that carry an optional `impersonado_id` claim. `CurrentUser` SHALL expose `impersonado_id: UUID | None`. `create_access_token` SHALL accept `impersonado_id` as an optional parameter (default None — all existing callers are unaffected). `get_current_user` SHALL extract the claim from the JWT if present.

#### Scenario: Normal login JWT has no impersonado_id
- **WHEN** a user logs in via `POST /api/v1/auth/login`
- **THEN** `current_user.impersonado_id` SHALL be `None`
- **AND** the decoded JWT payload SHALL NOT contain an `impersonado_id` key

#### Scenario: Impersonation JWT carries impersonado_id
- **WHEN** an ADMIN calls `POST /api/v1/auth/impersonate` with a valid `target_user_id`
- **THEN** the returned `access_token` SHALL decode to a payload containing `"impersonado_id": "<target_uuid_as_string>"`
- **AND** passing that token to any authenticated endpoint SHALL yield `CurrentUser(user_id=admin_id, impersonado_id=target_id, ...)`

---

### Requirement: POST /auth/impersonate starts a permissioned, audited impersonation session

#### Scenario: Authorized user starts impersonation successfully
- **WHEN** an authenticated user with the `impersonacion:usar` permission calls `POST /api/v1/auth/impersonate` with body `{"target_user_id": "<uuid>"}`
- **AND** the target user exists in the same tenant and has `is_active=True`
- **THEN** the response SHALL be HTTP 200 with body `{"access_token": "...", "impersonado_id": "<uuid>"}`
- **AND** an `audit_log` row SHALL exist with `accion="IMPERSONACION_INICIAR"`, `actor_id=requester_id`, `impersonado_id=target_id`, `tenant_id=requester_tenant_id`

#### Scenario: Target user not found in same tenant
- **WHEN** the `target_user_id` does not exist within the actor's tenant (regardless of whether it exists in another tenant)
- **THEN** the response SHALL be HTTP 404 Not Found

#### Scenario: Target user exists but is inactive
- **WHEN** the `target_user_id` exists in the same tenant but `is_active=False`
- **THEN** the response SHALL be HTTP 400 Bad Request with a descriptive detail message

#### Scenario: User without impersonacion:usar permission receives 403
- **WHEN** an authenticated user with the PROFESOR role (no `impersonacion:usar`) calls `POST /api/v1/auth/impersonate`
- **THEN** the response SHALL be HTTP 403 Forbidden

#### Scenario: Unauthenticated request receives 401
- **WHEN** `POST /api/v1/auth/impersonate` is called without Authorization header
- **THEN** the response SHALL be HTTP 401 Unauthorized

---

### Requirement: POST /auth/impersonate/end ends the session and logs FINALIZAR

#### Scenario: Active impersonation session ends cleanly
- **WHEN** a user currently holding an impersonating JWT (with `impersonado_id` claim) calls `POST /api/v1/auth/impersonate/end`
- **THEN** the response SHALL be HTTP 200 with a new `access_token` that does NOT contain an `impersonado_id` claim
- **AND** an `audit_log` row SHALL exist with `accion="IMPERSONACION_FINALIZAR"`, `actor_id=real_actor_id`, `impersonado_id=previously_impersonated_id`

#### Scenario: Calling /end when not currently impersonating returns 400
- **WHEN** an authenticated user with no active impersonation (normal JWT) calls `POST /api/v1/auth/impersonate/end`
- **THEN** the response SHALL be HTTP 400 with `{"detail": "No active impersonation session"}`

---

#### Scenario: Token expiry without calling /end does not log FINALIZAR (known MVP limitation)
- **WHEN** an impersonating access token expires without the user calling `POST /auth/impersonate/end`
- **THEN** no `IMPERSONACION_FINALIZAR` row SHALL be created (accepted MVP trade-off of stateless impersonation)
- **AND** the `IMPERSONACION_INICIAR` row SHALL remain as evidence that the session was started

---

### Requirement: Actions under impersonation are always attributed to the real actor

#### Scenario: Audit log records the real actor, not the impersonated user
- **WHEN** an ADMIN is impersonating user B
- **AND** any action that writes to `audit_log` is performed
- **THEN** `actor_id` in the audit row SHALL equal the ADMIN's `user_id`
- **AND** `impersonado_id` in the audit row SHALL equal user B's `user_id`
- **AND** user B's `user_id` SHALL NOT appear as `actor_id` in any row generated during the impersonation session
