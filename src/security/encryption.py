"""
GhostAttend — Credential Encryption

Fernet + PBKDF2 tabanlı kullanıcıya özel şifreleme.
Her kullanıcı için Telegram user_id + master key'den türetilmiş unique key kullanılır.
Master key .env'de yaşar, asla DB'ye yazılmaz.
"""

import base64
import json

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.core.exceptions import CredentialDecryptFailed


class CredentialVault:
    """
    Kullanıcı credential'larının şifreli saklanması ve çözümlenmesi.

    Her kullanıcı için Telegram user_id'sinden türetilmiş unique bir
    encryption key kullanır. Bu sayede bir kullanıcının key'i leak olsa
    bile diğer kullanıcılar etkilenmez.
    """

    def __init__(self, master_key: str | bytes):
        """
        Args:
            master_key: .env'den okunan master encryption key.
                        String veya bytes olabilir.
        """
        if isinstance(master_key, str):
            self.master_key = master_key.encode()
        else:
            self.master_key = master_key

    def _derive_key(self, user_id: int) -> bytes:
        """
        Kullanıcıya özel encryption key türet.

        PBKDF2-SHA256 ile master_key + user_id'den unique key üretir.
        OWASP 2024 önerisine uygun 480.000 iterasyon kullanılır.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=str(user_id).encode(),
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key))
        return key

    def encrypt(self, user_id: int, plaintext: str) -> bytes:
        """
        Metni kullanıcıya özel key ile şifrele.

        Args:
            user_id: Telegram user_id
            plaintext: Şifrelenecek metin (şifre, email vb.)

        Returns:
            Fernet encrypted bytes
        """
        f = Fernet(self._derive_key(user_id))
        return f.encrypt(plaintext.encode())

    def decrypt(self, user_id: int, ciphertext: bytes) -> str:
        """
        Şifreli metni kullanıcıya özel key ile çöz.

        Args:
            user_id: Telegram user_id
            ciphertext: Fernet encrypted bytes

        Returns:
            Çözümlenmiş plaintext string

        Raises:
            CredentialDecryptFailed: Master key değişmişse veya veri bozuksa
        """
        try:
            f = Fernet(self._derive_key(user_id))
            return f.decrypt(ciphertext).decode()
        except (InvalidToken, Exception) as e:
            raise CredentialDecryptFailed(
                f"Credential çözümlenirken hata: user_id={user_id}"
            ) from e

    def encrypt_cookies(self, user_id: int, cookies: list[dict]) -> bytes:
        """Session cookie'leri JSON olarak şifrele."""
        return self.encrypt(user_id, json.dumps(cookies))

    def decrypt_cookies(self, user_id: int, ciphertext: bytes) -> list[dict]:
        """Şifreli session cookie'leri çöz ve parse et."""
        raw = self.decrypt(user_id, ciphertext)
        return json.loads(raw)
