## ADDED Requirements

### Requirement: User can request password recovery

The system SHALL provide a public endpoint `POST /api/auth/forgot` that accepts `{"email": "user@example.com"}`. The system SHALL generate a single-use recovery token (opaque, 32 bytes, SHA-256 hash stored in DB), with a short expiry (15 minutes). For the MVP, the system SHALL return the recovery token in the response body. The system SHALL NOT reveal whether the email exists in the system (same response regardless).

#### Scenario: Successful forgot request
- **WHEN** a user sends `POST /api/auth/forgot` with an email that exists in the system
- **THEN** the system returns HTTP 200 with `{"detail": "If the email exists, a recovery token has been generated", "recovery_token": "<opaque_token>"}`
- **AND** a `RecoveryToken` record SHALL be created with the token hash, `user_id`, `tenant_id`, `expires_at` (15 min), and `used_at` = null

#### Scenario: Forgot request for non-existent email
- **WHEN** a user sends `POST /api/auth/forgot` with an email that does NOT exist
- **THEN** the system returns HTTP 200 with the exact same response as if the email existed
- **AND** no RecoveryToken record SHALL be created

#### Scenario: Duplicate forgot request
- **WHEN** a user sends `POST /api/auth/forgot` twice within 15 minutes for the same email
- **THEN** the system SHALL generate and return a new recovery token (invalidating the previous one, or allowing multiple valid tokens — TBD: allow multiple, only the first used wins)

### Requirement: User can reset password with recovery token

The system SHALL provide a public endpoint `POST /api/auth/reset` that accepts `{"token": "...", "new_password": "..."}`. The system SHALL validate the token (not expired, not used), hash the new password with Argon2id, update the user's password_hash, mark the token as used, and revoke all active sessions (all refresh tokens) for that user.

#### Scenario: Successful password reset
- **WHEN** a user sends `POST /api/auth/reset` with a valid recovery token and a new password (min 8 chars)
- **THEN** the system returns HTTP 200 with `{"detail": "Password reset successfully"}`
- **AND** the user's `password_hash` SHALL be updated with the new Argon2id hash
- **AND** the recovery token SHALL be marked as used (`used_at` set)
- **AND** all refresh tokens for that user SHALL be revoked

#### Scenario: Reset with expired token
- **WHEN** a user sends `POST /api/auth/reset` with a recovery token whose `expires_at` is in the past
- **THEN** the system returns HTTP 401 with `{"detail": "Token expired"}`

#### Scenario: Reset with already-used token
- **WHEN** a user sends `POST /api/auth/reset` with a recovery token that has been used before (`used_at` is not null)
- **THEN** the system returns HTTP 401 with `{"detail": "Token already used"}`

#### Scenario: Reset with invalid token
- **WHEN** a user sends `POST /api/auth/reset` with a token string that does not match any stored hash
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid token"}`

#### Scenario: Reset with weak password
- **WHEN** a user sends `POST /api/auth/reset` with a valid token but a password shorter than 8 characters
- **THEN** the system returns HTTP 422 with validation error
