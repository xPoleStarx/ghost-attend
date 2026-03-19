from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


def _normalize_secret(raw_secret: str) -> bytes:
    secret_bytes = bytes.fromhex(raw_secret)
    if len(secret_bytes) != 32:
        msg = "SECRET_KEY must decode to exactly 32 bytes."
        raise ValueError(msg)
    return base64.urlsafe_b64encode(secret_bytes)


@dataclass(slots=True)
class EncryptedValue:
    ciphertext: str
    key_version: str


class CredentialCipher:
    def __init__(self, raw_secret: str, key_version: str) -> None:
        self._fernet = Fernet(_normalize_secret(raw_secret))
        self._key_version = key_version

    @property
    def key_version(self) -> str:
        return self._key_version

    def encrypt(self, plaintext: str) -> EncryptedValue:
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return EncryptedValue(ciphertext=token, key_version=self._key_version)

    def decrypt(self, encrypted: EncryptedValue) -> str:
        try:
            value = self._fernet.decrypt(encrypted.ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            msg = "Unable to decrypt value with the configured key."
            raise ValueError(msg) from exc
        return value.decode("utf-8")
