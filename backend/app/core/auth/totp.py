"""TOTP (Time-based One-Time Password) utilities for 2FA.

Uses pyotp for TOTP generation and verification.
"""

import pyotp


def generate_totp_secret() -> str:
    """Generate a new base32-encoded TOTP secret (160 bits)."""
    return pyotp.random_base32(length=32)


def get_totp_uri(secret: str, email: str, issuer: str = "Trace") -> str:
    """Generate an otpauth:// URI for QR code provisioning.

    Args:
        secret: Base32-encoded TOTP secret.
        email: User's email (used as the account name).
        issuer: Display name for the authenticator app.

    Returns:
        A URI string compatible with `otpauth://totp/` schema.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret.

    Accepts a 1-step drift window (current +-1 interval).

    Args:
        secret: Base32-encoded TOTP secret.
        code: 6-digit code from authenticator app.

    Returns:
        True if the code is valid within the drift window.
    """
    if not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
