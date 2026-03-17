"""
GhostAttend — Abstract DYS Strategy

Farklı üniversite DYS'leri için ortak arayüz.
Generic strateji LLM agent'ı kullanır, spesifik stratejiler
bilinen DYS'ler için optimize edilmiş akışlar sağlar.
"""

from abc import ABC, abstractmethod

from src.core.logging import get_logger

log = get_logger(__name__)


class BaseDYSStrategy(ABC):
    """
    Abstract DYS strategy.
    Her üniversite DYS'i için özelleştirilmiş giriş ve
    ders arama stratejileri bu sınıftan türetilir.
    """

    def __init__(self, dys_url: str, dys_name: str = "generic"):
        self.dys_url = dys_url
        self.dys_name = dys_name

    @abstractmethod
    async def get_login_hints(self) -> dict:
        """
        DYS'e özgü login ipuçları döndür.

        Returns:
            {
                "login_url": str,           # Direkt login sayfası URL'i
                "username_selector": str,    # Kullanıcı adı alanı seçicisi (hint)
                "password_selector": str,    # Şifre alanı seçicisi (hint)
                "submit_selector": str,      # Giriş butonu seçicisi (hint)
                "post_login_indicator": str, # Başarılı giriş göstergesi
            }
        """
        ...

    @abstractmethod
    async def get_course_navigation_hints(self, course_name: str) -> dict:
        """
        DYS'te ders sayfasına ulaşmak için ipuçları.

        Returns:
            {
                "navigation_steps": list[str],  # Adım adım talimatlar
                "course_search_url": str | None,
                "meeting_link_patterns": list[str],  # "Teams", "Zoom" vs.
            }
        """
        ...

    def get_additional_task_instructions(self) -> str:
        """DYS'e özgü ek talimatlar (task prompt'a eklenir)."""
        return ""

    @classmethod
    def detect_dys(cls, url: str) -> "BaseDYSStrategy":
        """
        URL'den DYS'i tespit et ve uygun stratejiyi döndür.

        Bilinen DYS'ler için optimize edilmiş strateji,
        bilinmeyenler için generic strateji döndürür.
        """
        url_lower = url.lower()

        # Bilinen DYS pattern'ları
        # İleride buraya yeni üniversiteler eklenecek
        # if "obs.karadeniz.edu.tr" in url_lower:
        #     from src.agent.strategies.obs_karadeniz import OBSKaradenizStrategy
        #     return OBSKaradenizStrategy(url)
        # if "ubys.ege.edu.tr" in url_lower:
        #     from src.agent.strategies.ubys_ege import UBYSEgeStrategy
        #     return UBYSEgeStrategy(url)

        # Default: Generic strateji
        from src.agent.strategies.generic import GenericDYSStrategy

        return GenericDYSStrategy(url)
