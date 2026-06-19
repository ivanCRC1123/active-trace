## ADDED Requirements

### Requirement: User can refresh their token pair

The system SHALL provide a public endpoint `POST /api/auth/refresh` that accepts JSON body with `refresh_token` (string). The system SHALL validate the refresh token by looking up its SHA-256 hash in the database. On success, the system SHALL revoke the current refresh token and emit a new access token + refresh token pair (rotation). The new refresh token SHALL belong to the same token family (`family_id`). If the presented refresh token was already revoked, the system SHALL revoke ALL tokens in the same family (family revocation / token reuse detection).

#### Scenario: Successful token refresh
- **WHEN** a client sends `POST /api/auth/refresh` with a valid, non-revoked refresh token
- **THEN** the system returns HTTP 200 with a new `access_token`, new `refresh_token`, `token_type: "bearer"`, and `expires_in: 900`
- **AND** the previous refresh token SHALL be revoked (rotated)
- **AND** the new refresh token SHALL have the same `family_id` as the original

#### Scenario: Refresh with revoked token (reuse detection)
- **WHEN** a client sends `POST /api/auth/refresh` with a refresh token that was already revoked (previously rotated)
- **THEN** the system returns HTTP 401 with `{"detail": "Token has been revoked"}`
- **AND** the system SHALL revoke ALL tokens in the same family (family revocation)
- **AND** the user SHALL be forced to re-authenticate (previous valid tokens in that family also revoked)

#### Scenario: Refresh with non-existent token
- **WHEN** a client sends `POST /api/auth/refresh` with a token string that does not match any stored hash
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid token"}`

#### Scenario: Refresh with expired token
- **WHEN** a client sends `POST /api/auth/refresh` with a refresh token whose `expires_at` is in the past
- **THEN** the system returns HTTP 401 with `{"detail": "Token expired"}`

### Requirement: User can log out

The system SHALL provide an authenticated endpoint `POST /api/auth/logout` that requires a valid JWT access token (via `Authorization: Bearer` header). The system SHALL revoke the refresh token associated with the current session. The system SHALL accept an optional body with `refresh_token` (string) to identify which session to revoke; if not provided, the system SHALL NOT revoke any additional token.

#### Scenario: Successful logout
- **WHEN** an authenticated user sends `POST /api/auth/logout` with a valid refresh token in the body
- **THEN** the system returns HTTP 200 with `{"detail": "Logged out successfully"}`
- **AND** the specified refresh token SHALL be revoked (set `revoked_at`)
- **AND** the access token SHALL NOT be explicitly revoked (its short 15 min expiry is sufficient)

#### Scenario: Logout without authentication
- **WHEN** an unauthenticated client sends `POST /api/auth/logout` without a valid `Authorization: Bearer` header
- **THEN** the system returns HTTP 401 with `{"detail": "Missing or invalid token"}`
