## ADDED Requirements

### Requirement: User can enroll in 2FA TOTP

The system SHALL provide an authenticated endpoint `POST /api/auth/2fa/enroll` (requires valid JWT via `Authorization: Bearer`). The system SHALL generate a new TOTP secret (16 bytes, base32-encoded) per RFC 6238, store the encrypted secret in the user's `totp_secret` field, and return the provisioning URI (`otpauth://totp/activia-trace:{email}?secret={secret}&issuer=activia-trace`). Enrolling SHALL NOT activate 2FA; activation requires a successful verify call. If the user already has 2FA enabled, the system SHALL return an error unless they explicitly re-enroll.

#### Scenario: Successful 2FA enrollment
- **WHEN** an authenticated user sends `POST /api/auth/2fa/enroll` with no body or an empty body
- **THEN** the system returns HTTP 200 with `{"secret": "<base32_secret>", "uri": "otpauth://totp/activia-trace:{email}?secret={secret}&issuer=activia-trace"}`
- **AND** the `totp_secret` field in the user record SHALL be updated with the AES-256 encrypted secret
- **AND** `is_2fa_enabled` SHALL remain `false` until verified

#### Scenario: Re-enroll when 2FA already enabled
- **WHEN** a user with 2FA already enabled sends `POST /api/auth/2fa/enroll`
- **THEN** the system returns HTTP 409 with `{"detail": "2FA is already enabled. Disable it first to re-enroll."}`

### Requirement: User can verify 2FA TOTP code

The system SHALL provide an authenticated endpoint `POST /api/auth/2fa/verify` (requires valid JWT via `Authorization: Bearer`). The endpoint SHALL accept `{"code": "123456"}` (6-digit TOTP code). The system SHALL validate the code against the stored TOTP secret using `pyotp` with a window of 1 step (30s before/after). On success, the system SHALL set `is_2fa_enabled = true` for the user.

#### Scenario: Successful 2FA verification
- **WHEN** an authenticated user sends `POST /api/auth/2fa/verify` with a valid 6-digit TOTP code matching their enrolled secret
- **THEN** the system returns HTTP 200 with `{"detail": "2FA enabled successfully"}`
- **AND** the user's `is_2fa_enabled` field SHALL be set to `true`

#### Scenario: Invalid TOTP code
- **WHEN** an authenticated user sends `POST /api/auth/2fa/verify` with an invalid or expired 6-digit code
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid TOTP code"}`

#### Scenario: Verify without enrolling first
- **WHEN** an authenticated user who has never enrolled in 2FA sends `POST /api/auth/2fa/verify`
- **THEN** the system returns HTTP 400 with `{"detail": "No TOTP secret found. Enroll first."}`

### Requirement: 2FA gates login after credential validation

The system SHALL integrate 2FA into the login flow: if the user has `is_2fa_enabled = true`, the login endpoint SHALL NOT emit a token pair; instead, it SHALL return `{"requires_2fa": true, "session_token": "<opaque>"}`. The system SHALL provide `POST /api/auth/2fa/verify-login` (public, no auth required) that accepts `{"session_token": "...", "code": "123456"}`. On success, it SHALL emit the access + refresh token pair.

#### Scenario: Complete 2FA login flow
- **WHEN** a user with 2FA enabled completes password validation via login, receiving a session_token
- **AND** the user sends `POST /api/auth/2fa/verify-login` with a valid session_token and valid TOTP code
- **THEN** the system returns HTTP 200 with `access_token`, `refresh_token`, `token_type: "bearer"`, and `expires_in: 900`

#### Scenario: 2FA verify-login with invalid session_token
- **WHEN** a client sends `POST /api/auth/2fa/verify-login` with an invalid or expired session_token
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid or expired session token"}`

#### Scenario: 2FA verify-login with invalid TOTP code
- **WHEN** a client sends `POST /api/auth/2fa/verify-login` with a valid session_token but invalid TOTP code
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid TOTP code"}`
- **AND** the session_token SHALL remain valid (user can retry within 5 min window)
