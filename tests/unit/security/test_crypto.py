import pytest

from app.security.crypto import CredentialCipher, EncryptedValue


def test_encrypt_decrypt_roundtrip(cipher: CredentialCipher) -> None:
    encrypted = cipher.encrypt("super-secret")

    assert encrypted.key_version == "v1"
    assert cipher.decrypt(encrypted) == "super-secret"


def test_decrypt_invalid_token_raises(cipher: CredentialCipher) -> None:
    with pytest.raises(ValueError):
        cipher.decrypt(EncryptedValue(ciphertext="bad-token", key_version="v1"))
