## ADDED Requirements

### Requirement: Forgot password page lets user request a recovery token

`ForgotPasswordPage` SHALL render a form with a single `email` field (required, valid email format). On submission, it calls `POST /api/auth/forgot` with `{email}`. The backend always returns 200 (to avoid user enumeration). The page SHALL display a confirmation message regardless of whether the email exists, then show the recovery token if the backend returns one (MVP behavior — in production the token arrives by email).

#### Scenario: Forgot password form renders correctly
- **WHEN** `ForgotPasswordPage` is rendered
- **THEN** an email input and a submit button "Enviar instrucciones" are visible

#### Scenario: Empty email shows validation error
- **WHEN** the user clicks submit without entering an email
- **THEN** a validation error is displayed for the email field
- **AND** `POST /api/auth/forgot` is NOT called

#### Scenario: Valid submission shows confirmation message
- **GIVEN** MSW handler returns 200 `{"detail": "If that email exists, a recovery link was sent."}`
- **WHEN** the user enters a valid email and submits
- **THEN** the form is replaced by a confirmation message
- **AND** the message does NOT reveal whether the email exists in the system

#### Scenario: MVP recovery token display (if backend returns token)
- **GIVEN** MSW handler returns 200 with `{"recovery_token": "tok_abc123"}`
- **WHEN** the user submits the form
- **THEN** the recovery token is displayed in a visually distinct block (e.g., code element)
- **AND** a note "Este token solo es visible en desarrollo" is shown

---

### Requirement: Reset password page lets user set a new password using a recovery token

`ResetPasswordPage` SHALL read the recovery token from the URL query parameter `?token=...` or from a text input on the page. It SHALL render a form with `password` (new password) and `confirmPassword` fields. Zod schema validates that both match and that the password meets minimum requirements (min 8 characters). On submission it calls `POST /api/auth/reset` with `{token, new_password}`.

#### Scenario: Reset page reads token from URL param
- **GIVEN** the user navigates to `/reset-password?token=tok_abc123`
- **WHEN** `ResetPasswordPage` renders
- **THEN** the token is pre-filled (hidden field or read from URL) and ready to be sent

#### Scenario: Password mismatch shows validation error
- **GIVEN** the user enters different values in password and confirmPassword
- **WHEN** the user submits the form
- **THEN** a validation error "Las contraseñas no coinciden" is displayed
- **AND** `POST /api/auth/reset` is NOT called

#### Scenario: Successful reset redirects to login with success message
- **GIVEN** MSW handler for `POST /api/auth/reset` returns 200 `{"detail": "Password has been reset successfully."}`
- **WHEN** the user enters matching passwords and submits
- **THEN** the user is navigated to `/login`
- **AND** the login page displays a success notification "Tu contraseña fue actualizada. Podés iniciar sesión."

#### Scenario: Expired or invalid token shows error
- **GIVEN** MSW handler returns 401 `{"detail": "Invalid credentials"}`
- **WHEN** the user submits the reset form
- **THEN** an error message "El enlace de recuperación expiró o ya fue usado. Solicitá uno nuevo." is displayed
- **AND** a link to `/forgot-password` is shown

#### Scenario: Password too short shows validation error
- **GIVEN** the user enters a password shorter than 8 characters
- **WHEN** the user submits the form
- **THEN** a validation error "La contraseña debe tener al menos 8 caracteres" is displayed
