## MODIFIED Requirements

### Requirement: User can refresh tokens with rotation

The system SHALL provide a public endpoint `POST /api/auth/refresh` that accepts a `refresh_token` (string) in the JSON body. The system SHALL validate the token against its stored hash. On success, the system SHALL revoke the current refresh token and issue a new access + refresh token pair (rotation). The new access token SHALL include the user's role names in the `roles` claim, resolved from the `UserRol` table at the time of refresh. If the presented token is already revoked, the system SHALL revoke the entire token family (token reuse detection) and return HTTP 401.

#### Scenario: Successful refresh includes updated roles
- **WHEN** a user sends `POST /api/auth/refresh` with a valid, non-revoked refresh token
- **THEN** the system returns HTTP 200 with a new `access_token`, `refresh_token`, `token_type: "bearer"`, and `expires_in: 900`
- **AND** the new access_token SHALL contain the user's current role names in the `roles` claim
- **AND** the roles SHALL be freshly resolved from the `UserRol` table (not from the previous token)

#### Scenario: Refresh after role change reflects new roles
- **WHEN** a user's roles are modified in the `UserRol` table (role added or removed)
- **AND** the user then calls `POST /api/auth/refresh` with a valid refresh token
- **THEN** the new access_token SHALL reflect the current role assignments
- **AND** SHALL NOT use stale roles from the previous token

### Requirement: User can log out

The system SHALL provide a protected endpoint `POST /api/auth/logout` that accepts an optional `refresh_token` (string) in the JSON body. If a token is provided and it exists in the database and is not yet revoked, the system SHALL revoke it. This requirement is UNCHANGED from C-03; no role-related modifications needed.
