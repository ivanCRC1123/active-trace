"""Tests for core.encryption — AES-256-GCM round-trip and properties."""

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from app.core.encryption import decrypt, encrypt


@pytest.mark.asyncio
async def test_round_trip():
    """encrypt → decrypt recovers the original plaintext."""
    plaintext = "Hello, activia-trace!"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_different_ciphertexts_for_same_plaintext():
    """Two encryptions of the same text produce different outputs (random nonce)."""
    plaintext = "same text"
    c1 = encrypt(plaintext)
    c2 = encrypt(plaintext)
    assert c1 != c2


# ── Triangulation cases ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_string():
    """Empty string round-trips correctly."""
    plaintext = ""
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_utf8_special_chars():
    """UTF-8 characters (ñ, accents, emoji) round-trip correctly."""
    plaintext = "José Martínez — ñoño, café, corazón, été, 日本語"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_wrong_key_raises_invalid_tag(monkeypatch):
    """Decrypting with a wrong key raises InvalidTag."""
    plaintext = "secret data"
    ciphertext = encrypt(plaintext)

    # Temporarily change the encryption key in settings
    monkeypatch.setattr(
        "app.core.config.settings.ENCRYPTION_KEY",
        "z" * 32,  # Different 32-char key
    )
    with pytest.raises(InvalidTag):
        decrypt(ciphertext)


@pytest.mark.asyncio
async def test_corrupted_ciphertext_raises_error():
    """A tampered ciphertext raises InvalidTag."""
    plaintext = "tamper test"
    ciphertext = encrypt(plaintext)
    raw = bytearray(base64.urlsafe_b64decode(ciphertext))
    # Flip a bit in the ciphertext portion (after the 12-byte nonce)
    raw[15] ^= 0xFF
    corrupted = base64.urlsafe_b64encode(bytes(raw)).decode("utf-8")
    with pytest.raises(InvalidTag):
        decrypt(corrupted)


@pytest.mark.asyncio
async def test_no_plaintext_in_logs(caplog):
    """Encryption does not log plaintext or full ciphertext."""
    caplog.clear()
    plaintext = "sensitive-pii-data-123"
    encrypt(plaintext)
    for record in caplog.records:
        assert plaintext not in record.getMessage()
        # Full ciphertext should not appear either
        assert "sensitive" not in record.getMessage()
