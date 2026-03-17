"""
GhostAttend — Pytest Configuration & Fixtures

Tüm testlerin paylaştığı fixture'lar burada tanımlanır.
"""

import pytest

from src.security.encryption import CredentialVault


@pytest.fixture
def master_key() -> str:
    """Test için sabit master key."""
    return "test-master-key-not-for-production-use-only-32bytes!"


@pytest.fixture
def vault(master_key: str) -> CredentialVault:
    """Test CredentialVault instance'ı."""
    return CredentialVault(master_key)


@pytest.fixture
def sample_user_id() -> int:
    """Örnek Telegram user_id."""
    return 123456789


@pytest.fixture
def sample_courses() -> list[dict]:
    """Örnek parse edilmiş dersler."""
    return [
        {
            "ders_adi": "Kariyer Planlama",
            "gun": "Pazartesi",
            "baslangic_saati": "09:00",
            "bitis_saati": "10:30",
            "ogretim_uyesi": "Dr. Ahmet Yılmaz",
            "platform": "teams",
            "online_mi": True,
            "guvven_skoru": 0.95,
        },
        {
            "ders_adi": "Veri Yapıları",
            "gun": "Salı",
            "baslangic_saati": "13:00",
            "bitis_saati": "14:30",
            "ogretim_uyesi": "Prof. Ayşe Kaya",
            "platform": "teams",
            "online_mi": True,
            "guvven_skoru": 0.90,
        },
        {
            "ders_adi": "İngilizce",
            "gun": "Çarşamba",
            "baslangic_saati": "10:00",
            "bitis_saati": "11:30",
            "ogretim_uyesi": "Öğr. Gör. John Smith",
            "platform": "unknown",
            "online_mi": None,
            "guvven_skoru": 0.60,
        },
    ]
