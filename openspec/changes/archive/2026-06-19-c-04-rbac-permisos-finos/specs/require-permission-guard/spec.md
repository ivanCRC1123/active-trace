## ADDED Requirements

### Requirement: FastAPI dependency guard require_permission

The system SHALL provide a FastAPI callable dependency `require_permission(permission: str, scoped: bool = False)` that checks whether the current user has the required permission. If the user lacks the permission, the dependency SHALL raise HTTP 403 Forbidden. If `scoped=True`, the dependency SHALL return the scope (`'all'` or `'own'`) alongside the `CurrentUser` object for use by the endpoint's business logic.

#### Scenario: User with permission passes the guard
- **WHEN** an authenticated user with the ADMIN role calls an endpoint decorated with `Depends(require_permission("estructura_academica:gestionar"))`
- **THEN** the guard SHALL allow the request to proceed
- **AND** the endpoint handler SHALL receive the `CurrentUser` object

#### Scenario: User without permission receives 403
- **WHEN** an authenticated user with the ALUMNO role calls an endpoint decorated with `Depends(require_permission("calificaciones:importar"))`
- **THEN** the guard SHALL raise HTTP 403 with `{"detail": "Missing required permission: calificaciones:importar"}`

#### Scenario: Guard works with scoped=True and returns scope
- **WHEN** an authenticated user with the PROFESOR role calls an endpoint decorated with `Depends(require_permission("calificaciones:importar", scoped=True))`
- **THEN** the guard SHALL allow the request
- **AND** the injected value SHALL be a tuple `(CurrentUser, "own")`

#### Scenario: Anonymous user is rejected before permission check
- **WHEN** an unauthenticated request hits an endpoint decorated with `Depends(require_permission("..."))`
- **THEN** the guard SHALL raise HTTP 401 (from the embedded `get_current_user` dependency) before any permission check occurs

#### Scenario: Multiple permissions can be composed
- **WHEN** an endpoint requires two different permissions on different dependencies
- **AND** the user has only one of them
- **THEN** the first missing permission SHALL cause HTTP 403
- **AND** the specific missing permission SHALL be indicated in the error message
