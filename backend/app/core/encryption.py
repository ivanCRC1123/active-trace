"""AES-256-GCM encryption / decryption for PII attributes.

Uses ``cryptography.hazmat.primitives.ciphers.aead.AESGCM`` with a
random 12-byte nonce per encryption. The ciphertext is stored as a
single URL-safe base64 string containing ``nonce + ciphertext + tag``.

Never logs plaintext or full ciphertext values.
"""

import base64
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)

_NONCE_LENGTH = 12


def _get_key() -> bytes:
    """Return the AES-256 key as bytes."""
    return settings.ENCRYPTION_KEY.encode("utf-8")


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string with AES-256-GCM.

    Returns a URL-safe base64-encoded string that embeds both the
    random nonce (12 bytes) and the authenticated ciphertext.

    Args:
        plaintext: The string to encrypt.

    Returns:
        Base64-encoded ciphertext (nonce + ciphertext + tag).

    Raises:
        InvalidTag: If the encryption key is invalid.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    logger.info("Encryption successful.")
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")


def decrypt(ciphertext_b64: str) -> str:
    """Decrypt a ciphertext string previously produced by ``encrypt``.

    Args:
        ciphertext_b64: The base64-encoded ciphertext.

    Returns:
        The original plaintext string.

    Raises:
        InvalidTag: If the key is wrong or the ciphertext is corrupted.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(ciphertext_b64)
    nonce = raw[:_NONCE_LENGTH]
    ciphertext = raw[_NONCE_LENGTH:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    logger.info("Decryption successful.")
    return plaintext.decode("utf-8")
