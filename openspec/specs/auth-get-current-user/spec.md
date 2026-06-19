## ADDED Requirements

### Requirement: Authenticated endpoints can resolve current user from JWT

The system SHALL provide a FastAPI dependency `get_current_user` that extracts and verifies the JWT from the `Authorization: Bearer` header, resolves the user identity, tenant, and roles, and returns a `CurrentUser` object. The dependency SHALL be reusable on any endpoint that requires authentication. The dependency SHALL reject requests with missing, malformed, expired, or invalidly-signed tokens.

#### Scenario: Valid JWT resolves current user
- **WHEN** a request includes a valid `Authorization: Bearer <valid_access_token>` header
- **AND** the endpoint uses `Depends(get_current_user)`
- **THEN** the dependency SHALL return a `CurrentUser` object with `user_id` (UUID), `tenant_id` (UUID), and `roles` (list[str])
- **AND** the endpoint handler SHALL receive this object and can use it for authorization logic

#### Scenario: Missing Authorization header
- **WHEN** a request to a protected endpoint has no `Authorization` header
- **THEN** the dependency SHALL raise HTTP 401 with `{"detail": "Missing or invalid token"}`

#### Scenario: Expired JWT
- **WHEN** a request includes a JWT whose `exp` claim is in the past
- **THEN** the dependency SHALL raise HTTP 401 with `{"detail": "Token has expired"}`

#### Scenario: Invalid JWT signature
- **WHEN** a request includes a JWT with an invalid signature (tampered token)
- **THEN** the dependency SHALL raise HTTP 401 with `{"detail": "Invalid token"}`

### Requirement: CurrentUser is immutable — never overridden by request parameters

The `CurrentUser` object SHALL always be derived exclusively from the verified JWT. No parameter from request body, query string, path parameters, or headers SHALL be able to modify the identity, tenant, or roles of the current user. If business logic needs to compare a user ID from the request body with the current user's identity, the comparison SHALL be an explicit validation step, not an override.

#### Scenario: Body user_id does not override identity
- **WHEN** a protected endpoint receives a request with a valid JWT for user A
- **AND** the request body contains `{"user_id": "<different_uuid>"}`
- **THEN** `get_current_user` SHALL still return user A's identity
- **AND** any business logic comparing the body's user_id to the current user SHALL compare explicitly

### Requirement: CurrentUser includes tenant_id for multi-tenant isolation

The `CurrentUser.tenant_id` SHALL be used by repositories to scope all queries. Every protected endpoint SHOULD pass `current_user.tenant_id` to instantiate repositories. The tenant_id from the JWT SHALL match the tenant_id of the requested resource; if not, access SHALL be denied.

#### Scenario: Tenant isolation via CurrentUser
- **WHEN** a user from tenant A accesses an endpoint
- **AND** the endpoint creates a repository with `current_user.tenant_id`
- **THEN** all queries through that repository SHALL be scoped to tenant A only
- **AND** the user SHALL NOT be able to access tenant B's data
