## ADDED Requirements

### Requirement: AES-256-GCM encryption for sensitive PII fields

The system SHALL provide utility functions to encrypt and decrypt sensitive Personally Identifiable Information (PII) fields such as DNI, CUIL, CBU, and email addresses using AES-256-GCM authenticated encryption. The `ENCRYPTION_KEY` from application settings SHALL be used as the encryption key.

#### Scenario: Encrypt a plaintext string

- **WHEN** `encrypt(plaintext)` is called with a plaintext string
- **THEN** it returns a non-empty base64-encoded string
- **AND** the returned string contains a random nonce + ciphertext + authentication tag
- **AND** calling `encrypt` twice with the same plaintext produces different outputs (due to random nonce)

#### Scenario: Decrypt returns the original plaintext

- **WHEN** `decrypt(ciphertext)` is called with a valid ciphertext produced by `encrypt`
- **THEN** it returns the original plaintext string unchanged

#### Scenario: Round-trip for various input types

- **WHEN** encrypting and decrypting various inputs (ASCII, Unicode/UTF-8 with accents and ñ, empty string)
- **THEN** the decrypt output matches the original input exactly

#### Scenario: Decrypt fails with invalid key

- **WHEN** `decrypt` is called with a ciphertext that was encrypted with a different key
- **THEN** it raises an `InvalidTag` exception (or similar authentication error)
- **AND** does NOT return any data

#### Scenario: Decrypt fails with corrupted ciphertext

- **WHEN** `decrypt` is called with a tampered or corrupted ciphertext
- **THEN** it raises an authentication error
- **AND** does NOT return any data

### Requirement: Encryption must never log sensitive data

The encryption module SHALL NOT log the plaintext values or the full ciphertext under any circumstances. Log messages SHALL indicate operation success or failure without including the data being encrypted or decrypted.

#### Scenario: Encryption logs without plaintext

- **WHEN** `encrypt` is called
- **THEN** any log message produced SHALL NOT include the plaintext value
- **AND** any log message SHALL NOT include the full ciphertext
