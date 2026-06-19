## 1. Dependencies and configuration

- [x] 1.1 Add `python-jose[cryptography]`, `passlib[argon2]`, `argon2-cffi`, and `pyotp` to `backend/pyproject.toml`
- [x] 1.2 Add auth-related settings to `core/config.py`: `SECRET_KEY` (validated min 32 chars), `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15), `REFRESH_TOKEN_EXPIRE_DAYS` (default 7), `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, `RATE_LIMIT_MAX_ATTEMPTS` (default 5), `RATE_LIMIT_WINDOW_SECONDS` (default 60)
- [x] 1.3 Create `core/auth/` package with `__init__.py`

## 2. JWT and Argon2id utilities (`core/security.py`)

- [x] 2.1 (RED) Write `tests/test_security.py`
- [x] 2.2 (GREEN) Implement `core/security.py`
- [x] 2.3 (TRIANGULATE) Add additional tests

## 3. Models: User, RefreshToken, RecoveryToken

- [x] 3.1 (RED) Write `tests/test_user_model.py`
- [x] 3.2 (RED) Write `tests/test_refresh_token_model.py`
- [x] 3.3 (RED) Write `tests/test_recovery_token_model.py`
- [x] 3.4 (GREEN) Implement `models/user.py`
- [x] 3.5 (GREEN) Implement `models/refresh_token.py`
- [x] 3.6 (GREEN) Implement `models/recovery_token.py`
- [x] 3.7 (TRIANGULATE) Add additional tests

## 4. Pydantic schemas (`schemas/auth.py`)

- [x] 4.1 (RED) Write `tests/test_auth_schemas.py`
- [x] 4.2 (GREEN) Implement `schemas/auth.py`
- [x] 4.3 (TRIANGULATE) Add additional tests

## 5. Repositories

- [x] 5.1 (RED) Write `tests/test_user_repository.py`
- [x] 5.2 (RED) Write `tests/test_refresh_token_repository.py`
- [x] 5.3 (RED) Write `tests/test_recovery_token_repository.py`
- [x] 5.4 (GREEN) Implement `repositories/user_repository.py`
- [x] 5.5 (GREEN) Implement `repositories/refresh_token_repository.py`
- [x] 5.6 (GREEN) Implement `repositories/recovery_token_repository.py`
- [x] 5.7 (TRIANGULATE) Add additional tests

## 6. Rate limiter (`core/auth/rate_limiter.py`)

- [x] 6.1 (RED) Write `tests/test_rate_limiter.py`
- [x] 6.2 (GREEN) Implement `core/auth/rate_limiter.py`
- [x] 6.3 (TRIANGULATE) Add additional tests

## 7. 2FA TOTP utility (`core/auth/totp.py`)

- [x] 7.1 (RED) Write `tests/test_totp.py`
- [x] 7.2 (GREEN) Implement `core/auth/totp.py`
- [x] 7.3 (TRIANGULATE) Add additional tests

## 8. AuthService (`services/auth_service.py`)

- [x] 8.1 (RED) Write `tests/test_auth_service.py` (23 tests)
- [x] 8.2 (GREEN) Implement `app/core/auth/service.py`
- [x] 8.3 (TRIANGULATE) Add additional tests

## 9. `get_current_user` dependency (`core/dependencies.py`)

- [x] 9.1 (RED) Write `tests/test_get_current_user.py`
- [x] 9.2 (GREEN) Add `get_current_user` to `core/dependencies.py`
- [x] 9.3 (GREEN) Implement `CurrentUser` schema
- [x] 9.4 (TRIANGULATE) Add additional tests

## 10. Auth router (`api/v1/routers/auth.py`)

- [x] 10.1 (RED) Write `tests/test_auth_router_integration.py` (17 integration tests)
- [x] 10.2 (GREEN) Implement `api/v1/routers/auth.py`
- [x] 10.3 Register the auth router in `api/v1/routers/__init__.py` and `app/main.py`
- [x] 10.4 (TRIANGULATE) Add additional tests

## 11. Alembic migration 002

- [x] 11.1 Create Alembic migration 002: `a2b3c4d5e6f7_002_create_user_refresh_recovery.py`
- [x] 11.2 Review and clean migration
- [x] 11.3 Execute `alembic upgrade head` and verify tables
- [x] 11.4 Execute `alembic downgrade -1` and `alembic upgrade head`

## 12. Seed admin user

- [x] 12.1 Create `scripts/seed_admin.py` and `scripts/seed_tenant.py`
- [x] 12.2 Test seed scripts manually (both working)

## 13. Integration tests and final verification

- [x] 13.1 Fixtures in conftest + test file (`seeded_db`)
- [x] 13.2 Full test suite: **181 passed**, 0 failed
- [x] 13.3 E2E flows covered by integration tests
- [x] 13.4 Identity immutability verified
- [x] 13.5 ≤500 LOC per backend file ✓
- [x] 13.6 No PII in logs ✓
- [x] 13.7 All schemas use `extra='forbid'` ✓

## 14. Documentation and cleanup

- [ ] 14.1 Update `CHANGES.md` to mark C-03 as completed
- [ ] 14.2 Save architectural decisions to Engram
