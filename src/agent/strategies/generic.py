"""
GhostAttend — Generic DYS Strategy

Bilinmeyen/yeni üniversite DYS'leri için tamamen LLM agent'a
dayanan strateji. Sabit selector kullanmaz, agent ekranı okuyarak
navigasyon yapar.
"""

from src.agent.strategies.base import BaseDYSStrategy
from src.core.logging import get_logger

log = get_logger(__name__)


class GenericDYSStrategy(BaseDYSStrategy):
    """
    Genel amaçlı DYS stratejisi.
    Hiçbir DYS'e özgü bilgi kullanmaz, tamamen LLM agent'a güvenir.
    Bu sayede her üniversite DYS'i ile çalışabilir (agent-first yaklaşım).
    """

    def __init__(self, dys_url: str):
        super().__init__(dys_url, dys_name="generic")

    async def get_login_hints(self) -> dict:
        """Generic login ipuçları — agent kendi başına çözsün."""
        return {
            "login_url": self.dys_url,
            "username_selector": "",  # Agent ekrandan bulsun
            "password_selector": "",
            "submit_selector": "",
            "post_login_indicator": "",
        }

    async def get_course_navigation_hints(self, course_name: str) -> dict:
        """Generic navigasyon ipuçları."""
        return {
            "navigation_steps": [
                "Ana sayfada 'Derslerim', 'Ders Programı' veya benzeri bir menü bul",
                f"'{course_name}' dersini listeden bul",
                "Ders detay sayfasına git",
                "'Canlı Ders', 'Teams', 'Zoom', 'Toplantıya Katıl' gibi bir link ara",
            ],
            "course_search_url": None,
            "meeting_link_patterns": [
                "teams.microsoft.com",
                "zoom.us",
                "meet.google.com",
                "Canlı Ders",
                "Derse Katıl",
                "Toplantıya Katıl",
                "Join Meeting",
                "Sanal Sınıf",
                "Online Ders",
            ],
        }

    def get_additional_task_instructions(self) -> str:
        """Generic ek talimatlar."""
        return """
NOT: Bu DYS için özel bir strateji tanımlı değil. Tamamen ekranı okuyarak
ve gördüğüne göre karar vererek ilerle. Sayfadaki butonları, linkleri ve
menüleri dikkatlice incele. Türkçe ve İngilizce ifadelere dikkat et.

İPUÇLARI:
- Login sayfasında genellikle bir e-posta/kullanıcı adı ve şifre alanı vardır.
- "SSO", "Microsoft ile giriş", "Kurumsal Giriş" gibi butonlar varsa bunları tercih et.
- DYS'lerde dersler genellikle "Derslerim", "Öğrenci Paneli" veya sol menüde bulunur.
- Canlı ders linkleri ders detay sayfasında, duyurularda veya ders materyallerinde olabilir.
"""
