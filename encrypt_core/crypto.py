"""AES-256-GCM encryption for ComfyUI image files."""

from __future__ import annotations

import hashlib
import os
import secrets
from typing import Optional

MAGIC = b"CEAP\x01"
NONCE_SIZE = 12
KEY_SIZE = 32

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    AESGCM = None  # type: ignore[misc, assignment]


class EncryptionError(RuntimeError):
    pass


class KeyNotConfiguredError(EncryptionError):
    pass


_key: Optional[bytes] = None


def is_available() -> bool:
    return _HAS_CRYPTO


def is_encrypted(data: bytes) -> bool:
    return len(data) >= len(MAGIC) and data[: len(MAGIC)] == MAGIC


def key_configured() -> bool:
    return _key is not None and len(_key) == KEY_SIZE


def get_key_fingerprint() -> str:
    if not key_configured():
        return ""
    return hashlib.sha256(_key).hexdigest()[:16]


def set_key_from_bytes(key: bytes) -> None:
    global _key
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be exactly {KEY_SIZE} bytes")
    _key = key


def set_key_from_hex(hex_key: str) -> None:
    cleaned = hex_key.strip().replace("-", "").replace(" ", "")
    key = bytes.fromhex(cleaned)
    set_key_from_bytes(key)


def set_key_from_passphrase(passphrase: str, salt: Optional[bytes] = None) -> bytes:
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        600_000,
        dklen=KEY_SIZE,
    )
    set_key_from_bytes(key)
    return salt


def _require_key() -> bytes:
    if not _HAS_CRYPTO:
        raise EncryptionError(
            "cryptography package is required. Install with: pip install cryptography"
        )
    if not key_configured():
        raise KeyNotConfiguredError(
            "Encryption key is not configured. "
            "Set COMFYUI_ENCRYPT_KEY (64-char hex) or create encrypt_key.txt in the plugin folder."
        )
    return _key  # type: ignore[return-value]


def encrypt_bytes(plaintext: bytes) -> bytes:
    key = _require_key()
    nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return MAGIC + nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    if not is_encrypted(data):
        return data
    if len(data) < len(MAGIC) + NONCE_SIZE + 16:
        raise EncryptionError("Encrypted file is too short or corrupted")
    key = _require_key()
    nonce = data[len(MAGIC) : len(MAGIC) + NONCE_SIZE]
    ciphertext = data[len(MAGIC) + NONCE_SIZE :]
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def read_file_maybe_encrypted(path: str) -> bytes:
    from .io_bypass import _original_open, bypass_encryption

    with bypass_encryption():
        with _original_open(path, "rb") as f:
            data = f.read()
    if is_encrypted(data):
        return decrypt_bytes(data)
    return data


def write_encrypted_file(path: str, plaintext: bytes) -> None:
    from .io_bypass import _original_open, bypass_encryption

    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    encrypted = encrypt_bytes(plaintext)
    with bypass_encryption():
        with _original_open(path, "wb") as f:
            f.write(encrypted)
