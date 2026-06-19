## ADDED Requirements

### Requirement: Rate limit login attempts per IP+tenant_code+email

The system SHALL enforce a rate limit of maximum 5 login attempts per 60-second sliding window, keyed by the combination of client IP, `tenant_code`, and email address. The rate limiter SHALL be applied to `POST /api/auth/login`. The rate limiter SHALL use an in-memory sliding window algorithm. When the limit is exceeded, the system SHALL return HTTP 429 with a `Retry-After` header indicating seconds until the rate limit resets.

#### Scenario: Rate limit not exceeded
- **WHEN** a client makes 4 login attempts from the same IP, `tenant_code`, and email within 60 seconds
- **THEN** each attempt SHALL be processed normally (return 401 for invalid credentials or 200 for valid)

#### Scenario: Rate limit exceeded
- **WHEN** a client makes 6 or more login attempts from the same IP, `tenant_code`, and email within 60 seconds
- **THEN** the 6th attempt SHALL return HTTP 429 with `{"detail": "Too many requests. Try again later."}`
- **AND** the response SHALL include a `Retry-After` header with the number of seconds remaining

#### Scenario: Rate limit resets after window
- **WHEN** a client exceeds the rate limit
- **AND** waits longer than 60 seconds since the first attempt
- **THEN** the next login attempt SHALL be processed normally

### Requirement: Rate limit does not apply to other auth endpoints

The rate limiter SHALL ONLY apply to `POST /api/auth/login`. Other auth endpoints (refresh, forgot, reset, 2fa, logout) SHALL NOT be rate-limited in the MVP. (They may be added in future iterations.)

#### Scenario: Refresh endpoint not rate-limited
- **WHEN** a client makes more than 5 `POST /api/auth/refresh` calls from the same IP within 60 seconds
- **THEN** each call SHALL be processed normally (no 429 from rate limiting)

### Requirement: Rate limiter is in-memory (single-process)

The rate limiter SHALL store state in a Python dictionary with `asyncio.Lock` for thread safety. The state SHALL NOT persist across server restarts. A future iteration SHALL migrate to Redis for multi-worker deployments.

#### Scenario: Rate limit state survives across requests
- **WHEN** a client makes 5 login attempts
- **AND** a subsequent 6th attempt is made from the same IP+tenant_code+email
- **THEN** the 6th attempt SHALL be rate limited (429), proving state is maintained between requests
