"""Tests for crypto helpers."""

from __future__ import annotations

import pytest

from custom_components.liberated_bread.codec.crypto import (
    _key_bytes,
    encrypt_aes_128_ecb,
    pkcs7_pad,
)


@pytest.mark.parametrize(
    ("payload", "expected_len", "last_byte"),
    [(b"", 16, 16), (b"abc", 16, 13), (b"1234567890abcdef", 32, 16)],
)
def test_pkcs7_padding(payload, expected_len, last_byte) -> None:
    padded = pkcs7_pad(payload)
    assert len(padded) == expected_len
    assert padded[-1] == last_byte


def test_aes_128_ecb_encrypt_known_vector() -> None:
    encrypted = encrypt_aes_128_ecb(
        bytes.fromhex("00112233445566778899aabbccddeeff"),
        "000102030405060708090a0b0c0d0e0f",
    )
    assert encrypted.hex() == (
        "69c4e0d86a7b0430d8cdb78070b4c55a"
        "954f64f2e4e86e9eee82d20216684899"
    )


def test_key_parsing_hex_bytes_and_spaced_hex() -> None:
    assert _key_bytes(bytes(range(16))) == bytes(range(16))
    assert _key_bytes("000102030405060708090a0b0c0d0e0f") == bytes(range(16))
    assert _key_bytes("00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e 0f") == bytes(range(16))


def test_key_wrong_length_raises() -> None:
    with pytest.raises(ValueError, match="16 bytes"):
        _key_bytes("short")
