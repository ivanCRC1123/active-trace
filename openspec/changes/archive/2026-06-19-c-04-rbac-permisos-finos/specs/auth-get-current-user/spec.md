## ADDED Requirements

### Requirement: CurrentUser roles are populated from JWT (which was populated from UserRol)

The `get_current_user` dependency already parses the `roles` claim from the JWT. After C-04, this claim contains actual role names resolved from `UserRol` at login/refresh time. No code change is needed in `get_current_user` itself — the change is upstream in `AuthService._issue_tokens()` and `refresh()`. However, this spec formalizes the expected behavior of `CurrentUser.roles` being non-empty when the user has role assignments.

#### Scenario: CurrentUser.roles contains role names from JWT
- **WHEN** a user with ADMIN role logs in and receives an access_token
- **AND** the user calls a protected endpoint with that token
- **THEN** `get_current_user` SHALL return a `CurrentUser` object
- **AND** `CurrentUser.roles` SHALL be a list containing the role name strings (e.g., `["ADMIN"]`)

#### Scenario: CurrentUser.roles is empty for users without roles
- **WHEN** a user with no `UserRol` entries logs in and receives an access_token
- **AND** the user calls a protected endpoint with that token
- **THEN** `CurrentUser.roles` SHALL be `[]`

## MODIFIED Requirements

### Requirement: Authenticated endpoints can resolve current user from JWT

The system SHALL provide a FastAPI dependency `get_current_user` that extracts and verifies the JWT from the `Authorization: Bearer` header, resolves the user identity, tenant, and roles, and returns a `CurrentUser` object. The dependency SHALL be reusable on any endpoint that requires authentication. The dependency SHALL reject requests with missing, malformed, expired, or invalidly-signed tokens. The `roles` field SHALL be populated from the JWT's `roles` claim, which is populated from `UserRol` at token issuance time.

#### Scenario: Valid JWT resolves current user with roles
- **WHEN** a request includes a valid `Authorization: Bearer <valid_access_token>` header
- **AND** the access_token has `roles: ["ADMIN", "COORDINADOR"]`
- **AND** the endpoint uses `Depends(get_current_user)`
- **THEN** the dependency SHALL return a `CurrentUser` object with `user_id` (UUID), `tenant_id` (UUID), and `roles` (list[str])
- **AND** `CurrentUser.roles` SHALL be `["ADMIN", "COORDINADOR"]`

### Requirement: CurrentUser is immutable — never overridden by request parameters

UNCHANGED from C-03. The `CurrentUser` object SHALL always be derived exclusively from the verified JWT. No parameter from request body, query string, path parameters, or headers SHALL be able to modify the identity, tenant, or roles of the current user.

### Requirement: CurrentUser includes tenant_id for multi-tenant isolation

UNCHANGED from C-03. The `CurrentUser.tenant_id` SHALL be used by repositories to scope all queries.
