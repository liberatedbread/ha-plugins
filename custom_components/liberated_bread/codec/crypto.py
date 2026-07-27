"""Encryption helpers for supported OpenGreenIoT devices."""

from __future__ import annotations

try:
    from Crypto.Cipher import AES
except ImportError as err:  # pragma: no cover - HA installs requirements.
    AES = None  # type: ignore[assignment]
    _IMPORT_ERROR = err
else:
    _IMPORT_ERROR = None

def encrypt_aes_128_ecb(payload: bytes, key: bytes | str) -> bytes:
    """PKCS7-pad and encrypt a payload with AES-128-ECB."""
    if AES is None:
        raise RuntimeError("pycryptodome is required for AES encryption") from _IMPORT_ERROR
    key_bytes = _key_bytes(key)
    padded = pkcs7_pad(payload, 16)
    return AES.new(key_bytes, AES.MODE_ECB).encrypt(padded)


def pkcs7_pad(payload: bytes, block_size: int = 16) -> bytes:
    """Apply PKCS7 padding."""
    pad_len = block_size - (len(payload) % block_size)
    return payload + bytes([pad_len]) * pad_len


def _key_bytes(key: bytes | str) -> bytes:
    if isinstance(key, bytes):
        key_bytes = key
    else:
        text = key.replace(" ", "").replace(":", "")
        key_bytes = bytes.fromhex(text) if len(text) == 32 else text.encode()
    if len(key_bytes) != 16:
        raise ValueError("AES-128 key must be exactly 16 bytes")
    return key_bytes
