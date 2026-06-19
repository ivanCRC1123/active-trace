## ADDED Requirements

### Requirement: User can log in with email, password and tenant code

The system SHALL provide a public endpoint `POST /api/auth/login` that accepts JSON body with `tenant_code` (string), `email` (string), and `password` (string). The system SHALL resolve the tenant from `tenant_code`, then validate credentials against the stored Argon2id hash for that tenant. On success, the system SHALL emit a JWT access token (15 min expiry) and a refresh token (opaque, 7 days, with rotation). If the user has 2FA enabled, the system SHALL return a `requires_2fa` response with a session_token instead of the token pair. The email lookup SHALL be case-insensitive within the tenant scope.

#### Scenario: Successful login without 2FA
- **WHEN** a user sends `POST /api/auth/login` with valid `tenant_code`, `email`, and `password`
- **THEN** the system returns HTTP 200 with `access_token`, `refresh_token`, `token_type: "bearer"`, and `expires_in: 900` (15 min)
- **AND** the access_token SHALL be a valid JWT signed with HS256 containing claims `sub` (user UUID), `tenant_id` (UUID), `roles` (list of strings), and `exp` (timestamp)
- **AND** the `tenant_id` claim SHALL correspond to the tenant resolved from the provided `tenant_code`

#### Scenario: Login with invalid password
- **WHEN** a user sends `POST /api/auth/login` with a valid `tenant_code` and email but wrong password
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid credentials"}`
- **AND** the system SHALL NOT reveal whether the tenant/email exists or the password is wrong (same message for all)

#### Scenario: Login with non-existent email
- **WHEN** a user sends `POST /api/auth/login` with a valid `tenant_code` but an email that does not exist in that tenant
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid credentials"}`

#### Scenario: Login with non-existent tenant_code
- **WHEN** a user sends `POST /api/auth/login` with a `tenant_code` that does not match any tenant in the system
- **THEN** the system returns HTTP 401 with `{"detail": "Invalid credentials"}`
- **AND** the system SHALL NOT reveal whether the tenant exists or not (same message as invalid credentials)

#### Scenario: Login with inactive user
- **WHEN** a user whose `is_active` is `false` sends `POST /api/auth/login` with valid `tenant_code`, email, and password
- **THEN** the system returns HTTP 401 with `{"detail": "Account is inactive"}`

#### Scenario: Login with 2FA enabled returns requires_2fa
- **WHEN** a user with 2FA enabled sends `POST /api/auth/login` with valid `tenant_code`, email, and password
- **THEN** the system returns HTTP 200 with `{"requires_2fa": true, "session_token": "<opaque_string>"}` and no access/refresh tokens
- **AND** the session_token SHALL be a one-time opaque token valid for 5 minutes

#### Scenario: Login rate limited
- **WHEN** more than 5 login attempts are made from the same IP+tenant_code+email combination within 60 seconds
- **THEN** the system returns HTTP 429 with `{"detail": "Too many requests. Try again later."}` and a `Retry-After` header

#### Scenario: Malformed request body
- **WHEN** a user sends `POST /api/auth/login` with missing `tenant_code`, `email`, or `password` fields
- **THEN** the system returns HTTP 422 with validation error details
- **AND** extra fields in the request body SHALL cause HTTP 422 (Pydantic `extra='forbid'`)

#### Scenario: Identity immutability by parameter
- **WHEN** any authenticated request includes a `user_id` or `tenant_id` in the request body, query string, or headers intending to override identity
- **THEN** the system SHALL ignore such parameters for identity resolution
- **AND** the identity SHALL always be derived exclusively from the verified JWT
