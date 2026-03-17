"""
GhostAttend — CredentialVault Unit Tests

Şifreleme/çözümleme, kullanıcı izolasyonu ve edge case testleri.
"""

import pytest

from src.security.encryption import CredentialVault
from src.core.exceptions import CredentialDecryptFailed


class TestCredentialVault:
    """CredentialVault encrypt/decrypt testleri."""

    def test_encrypt_decrypt_roundtrip(self, vault: CredentialVault, sample_user_id: int):
        """Temel encrypt/decrypt döngüsü çalışmalı."""
        original = "super_secret_password"
        encrypted = vault.encrypt(sample_user_id, original)
        decrypted = vault.decrypt(sample_user_id, encrypted)

        assert decrypted == original

    def test_encrypted_is_not_plaintext(self, vault: CredentialVault, sample_user_id: int):
        """Şifrelenmiş veri plaintext olmamalı."""
        original = "super_secret_password"
        encrypted = vault.encrypt(sample_user_id, original)

        assert encrypted != original.encode()
        assert original.encode() not in encrypted

    def test_different_users_different_ciphertext(self, vault: CredentialVault):
        """Farklı kullanıcılar için aynı plaintext farklı ciphertext üretmeli."""
        plaintext = "same_password"

        encrypted_1 = vault.encrypt(111, plaintext)
        encrypted_2 = vault.encrypt(222, plaintext)

        assert encrypted_1 != encrypted_2

    def test_user_cannot_decrypt_others(self, vault: CredentialVault):
        """Bir kullanıcının key'i ile başka kullanıcının verisi çözülememeli."""
        secret = "my_secret"
        encrypted = vault.encrypt(111, secret)

        with pytest.raises(CredentialDecryptFailed):
            vault.decrypt(222, encrypted)

    def test_wrong_master_key_fails(self, sample_user_id: int):
        """Yanlış master key ile decrypt başarısız olmalı."""
        vault1 = CredentialVault("correct-master-key-for-testing-32bytes!!")
        vault2 = CredentialVault("wrong-master-key-for-this-test-32bytes!!")

        encrypted = vault1.encrypt(sample_user_id, "secret")

        with pytest.raises(CredentialDecryptFailed):
            vault2.decrypt(sample_user_id, encrypted)

    def test_encrypt_decrypt_cookies(self, vault: CredentialVault, sample_user_id: int):
        """Cookie encrypt/decrypt çalışmalı."""
        cookies = [
            {"name": "session", "value": "abc123", "domain": ".microsoft.com"},
            {"name": "auth", "value": "xyz789", "domain": ".teams.microsoft.com"},
        ]

        encrypted = vault.encrypt_cookies(sample_user_id, cookies)
        decrypted = vault.decrypt_cookies(sample_user_id, encrypted)

        assert decrypted == cookies
        assert len(decrypted) == 2
        assert decrypted[0]["name"] == "session"

    def test_encrypt_empty_string(self, vault: CredentialVault, sample_user_id: int):
        """Boş string de şifrelenmeli."""
        encrypted = vault.encrypt(sample_user_id, "")
        decrypted = vault.decrypt(sample_user_id, encrypted)
        assert decrypted == ""

    def test_encrypt_unicode(self, vault: CredentialVault, sample_user_id: int):
        """Unicode karakterli şifre doğru çalışmalı."""
        password = "şifre_Ğüİ_密码_🔒"
        encrypted = vault.encrypt(sample_user_id, password)
        decrypted = vault.decrypt(sample_user_id, encrypted)
        assert decrypted == password

    def test_string_master_key(self, sample_user_id: int):
        """String olarak verilen master key çalışmalı."""
        vault = CredentialVault("string-master-key-for-testing!!")
        encrypted = vault.encrypt(sample_user_id, "test")
        decrypted = vault.decrypt(sample_user_id, encrypted)
        assert decrypted == "test"

    def test_bytes_master_key(self, sample_user_id: int):
        """Bytes olarak verilen master key çalışmalı."""
        vault = CredentialVault(b"bytes-master-key-for-testing!!")
        encrypted = vault.encrypt(sample_user_id, "test")
        decrypted = vault.decrypt(sample_user_id, encrypted)
        assert decrypted == "test"
