## MODIFIED Requirements

### Requirement: User can log in with email, password and tenant code

The system SHALL provide a public endpoint `POST /api/auth/login` that accepts JSON body with `tenant_code` (string), `email` (string), and `password` (string). The system SHALL resolve the tenant from `tenant_code`, then validate credentials against the stored Argon2id hash for that tenant. On success, the system SHALL emit a JWT access token (15 min expiry) and a refresh token (opaque, 7 days, with rotation). If the user has 2FA enabled, the system SHALL return a `requires_2fa` response with a session_token instead of the token pair. The email lookup SHALL be case-insensitive within the tenant scope. The access token SHALL include the user's role names in the `roles` claim, resolved from the `UserRol` table at the time of login. If the user has no roles assigned, the `roles` claim SHALL be an empty list.

#### Scenario: Successful login without 2FA includes roles
- **WHEN** a user sends `POST /api/auth/login` with valid `tenant_code`, `email`, and `password`
- **AND** the user has role assignments in the `user_rol` table
- **THEN** the system returns HTTP 200 with `access_token`, `refresh_token`, `token_type: "bearer"`, and `expires_in: 900` (15 min)
- **AND** the access_token SHALL be a valid JWT signed with HS256 containing claims `sub` (user UUID), `tenant_id` (UUID), `roles` (list of role name strings), and `exp` (timestamp)
- **AND** the `roles` claim SHALL contain the name of each role assigned to the user (e.g., `["ADMIN"]`)
- **AND** the `roles` claim SHALL NOT contain permissions — only role names

#### Scenario: Successful login for user with no roles
- **WHEN** a user sends `POST /api/auth/login` with valid credentials
- **AND** the user has no entries in the `user_rol` table
- **THEN** the access_token SHALL contain `"roles": []`

#### Scenario: Login with 2FA enabled returns requires_2fa (no roles in response)
- **WHEN** a user with 2FA enabled sends `POST /api/auth/login` with valid `tenant_code`, `email`, and `password`
- **THEN** the system returns HTTP 200 with `{"requires_2fa": true, "session_token": "<opaque_string>"}`
- **AND** no access or refresh tokens are returned at this stage
- **AND** roles are resolved only after 2FA verification completes
