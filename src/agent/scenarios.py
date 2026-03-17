"""
GhostAttend — Senaryo Matrisi

Agent çalışması sırasında oluşabilecek 10 senaryo ve
her biri için otomatik hata kurtarma stratejileri.
architecture.md Section 10
"""

from dataclasses import dataclass
from enum import Enum

from src.core.logging import get_logger

log = get_logger(__name__)


class ScenarioType(str, Enum):
    """Tespit edilebilen senaryo tipleri."""

    HAPPY_PATH = "happy_path"
    DYS_LOGIN_FAIL = "dys_login_fail"
    DYS_MAINTENANCE = "dys_maintenance"
    LINK_NOT_FOUND = "link_not_found"
    MEETING_NOT_STARTED = "meeting_not_started"
    MFA_SMS = "mfa_sms"
    MFA_AUTHENTICATOR = "mfa_authenticator"
    JOIN_FAILED = "join_failed"
    PAGE_FROZEN = "page_frozen"
    COOKIE_EXPIRED = "cookie_expired"
    SESSION_KICKED = "session_kicked"
    NETWORK_ERROR = "network_error"


class RecoveryAction(str, Enum):
    """Kurtarma eylem tipleri."""

    CONTINUE = "continue"          # Devam et
    RETRY = "retry"                # Yeniden dene
    RETRY_WITH_DELAY = "retry_delay"  # Gecikmeli yeniden dene
    RELOGIN = "relogin"            # Tekrar giriş yap
    REQUEST_MFA = "request_mfa"    # Kullanıcıdan MFA iste
    NOTIFY_USER = "notify_user"    # Kullanıcıyı bilgilendir
    ABORT = "abort"                # Oturumu sonlandır
    WAIT_AND_RETRY = "wait_retry"  # Bekle ve tekrar dene


@dataclass
class ScenarioConfig:
    """Bir senaryo için yapılandırma."""

    scenario_type: ScenarioType
    description: str
    max_retries: int
    recovery_action: RecoveryAction
    retry_delay_seconds: int
    notify_user: bool
    notification_message: str
    is_fatal: bool  # True ise kullanıcı müdahalesi gerekli


# ── 10 Senaryo Tanımları ──

SCENARIO_MATRIX: dict[ScenarioType, ScenarioConfig] = {
    # 1. Happy Path — Her şey yolunda
    ScenarioType.HAPPY_PATH: ScenarioConfig(
        scenario_type=ScenarioType.HAPPY_PATH,
        description="Tüm adımlar başarılı, ders katılımı tamamlandı",
        max_retries=0,
        recovery_action=RecoveryAction.CONTINUE,
        retry_delay_seconds=0,
        notify_user=True,
        notification_message="✅ {course_name} dersine başarıyla katıldın!",
        is_fatal=False,
    ),

    # 2. DYS Login Başarısız
    ScenarioType.DYS_LOGIN_FAIL: ScenarioConfig(
        scenario_type=ScenarioType.DYS_LOGIN_FAIL,
        description="DYS giriş başarısız — şifre yanlış veya hesap kilitli",
        max_retries=1,
        recovery_action=RecoveryAction.NOTIFY_USER,
        retry_delay_seconds=0,
        notify_user=True,
        notification_message=(
            "❌ DYS giriş başarısız!\n"
            "Şifren yanlış olabilir.\n"
            "/reauth ile yeniden giriş bilgilerini güncelle."
        ),
        is_fatal=True,
    ),

    # 3. DYS Bakım Modu
    ScenarioType.DYS_MAINTENANCE: ScenarioConfig(
        scenario_type=ScenarioType.DYS_MAINTENANCE,
        description="DYS bakım modunda veya erişilemiyor",
        max_retries=3,
        recovery_action=RecoveryAction.RETRY_WITH_DELAY,
        retry_delay_seconds=120,  # 2dk sonra tekrar dene
        notify_user=True,
        notification_message=(
            "⚠️ DYS şu anda bakımda. {retry_count}/{max_retries} "
            "deneme yapılıyor ({retry_delay}sn arayla)..."
        ),
        is_fatal=False,
    ),

    # 4. Ders Linki Bulunamadı
    ScenarioType.LINK_NOT_FOUND: ScenarioConfig(
        scenario_type=ScenarioType.LINK_NOT_FOUND,
        description="DYS'te ders için canlı ders linki bulunamadı",
        max_retries=2,
        recovery_action=RecoveryAction.RETRY_WITH_DELAY,
        retry_delay_seconds=60,
        notify_user=True,
        notification_message=(
            "⚠️ {course_name} için canlı ders linki bulunamadı.\n"
            "Hoca henüz paylaşmamış olabilir. {retry_count}/{max_retries} "
            "yeniden deneniyor..."
        ),
        is_fatal=False,
    ),

    # 5. Toplantı Henüz Başlamamış
    ScenarioType.MEETING_NOT_STARTED: ScenarioConfig(
        scenario_type=ScenarioType.MEETING_NOT_STARTED,
        description="Teams/Zoom toplantısı henüz başlatılmamış",
        max_retries=5,
        recovery_action=RecoveryAction.WAIT_AND_RETRY,
        retry_delay_seconds=60,  # Her dakika kontrol
        notify_user=False,  # Beklenen durum, gereksiz bildirim gönderme
        notification_message="",
        is_fatal=False,
    ),

    # 6. MFA — SMS Kodu
    ScenarioType.MFA_SMS: ScenarioConfig(
        scenario_type=ScenarioType.MFA_SMS,
        description="SMS ile MFA kodu gerekli",
        max_retries=0,
        recovery_action=RecoveryAction.REQUEST_MFA,
        retry_delay_seconds=0,
        notify_user=True,
        notification_message=(
            "🔐 SMS ile doğrulama kodu gönderildi.\n"
            "Telefonuna gelen kodu buraya yaz.\n"
            "⏰ 120 saniye süren var."
        ),
        is_fatal=False,  # Kullanıcı kodu girerse devam eder
    ),

    # 7. MFA — Authenticator Push
    ScenarioType.MFA_AUTHENTICATOR: ScenarioConfig(
        scenario_type=ScenarioType.MFA_AUTHENTICATOR,
        description="Microsoft Authenticator push onayı gerekli",
        max_retries=0,
        recovery_action=RecoveryAction.REQUEST_MFA,
        retry_delay_seconds=0,
        notify_user=True,
        notification_message=(
            "📱 Microsoft Authenticator'dan gelen bildirimi onayla.\n"
            "Onayladıktan sonra /confirmed yaz.\n"
            "⏰ 60 saniye süren var."
        ),
        is_fatal=False,
    ),

    # 8. Derse Katılım Başarısız
    ScenarioType.JOIN_FAILED: ScenarioConfig(
        scenario_type=ScenarioType.JOIN_FAILED,
        description="Teams/Zoom toplantısına katılım başarısız",
        max_retries=2,
        recovery_action=RecoveryAction.RETRY,
        retry_delay_seconds=15,
        notify_user=True,
        notification_message=(
            "⚠️ Derse katılım başarısız oldu.\n"
            "Yeniden deneniyor ({retry_count}/{max_retries})..."
        ),
        is_fatal=False,
    ),

    # 9. Sayfa Donması
    ScenarioType.PAGE_FROZEN: ScenarioConfig(
        scenario_type=ScenarioType.PAGE_FROZEN,
        description="Tarayıcı sayfası dondu veya yanıt vermiyor",
        max_retries=2,
        recovery_action=RecoveryAction.RETRY,
        retry_delay_seconds=10,
        notify_user=False,
        notification_message="",
        is_fatal=False,
    ),

    # 10. Cookie Süresi Dolmuş
    ScenarioType.COOKIE_EXPIRED: ScenarioConfig(
        scenario_type=ScenarioType.COOKIE_EXPIRED,
        description="Kayıtlı session cookie'si geçersiz",
        max_retries=1,
        recovery_action=RecoveryAction.RELOGIN,
        retry_delay_seconds=0,
        notify_user=False,
        notification_message="",
        is_fatal=False,
    ),

    # 11. Oturum Atıldı (Session Kicked)
    ScenarioType.SESSION_KICKED: ScenarioConfig(
        scenario_type=ScenarioType.SESSION_KICKED,
        description="Başka bir cihazdan oturum açıldı veya ders bittiği için atıldı",
        max_retries=1,
        recovery_action=RecoveryAction.RETRY,
        retry_delay_seconds=5,
        notify_user=True,
        notification_message="⚠️ Oturumdan atıldın. Yeniden bağlanılıyor...",
        is_fatal=False,
    ),

    # 12. Ağ Hatası
    ScenarioType.NETWORK_ERROR: ScenarioConfig(
        scenario_type=ScenarioType.NETWORK_ERROR,
        description="İnternet bağlantısı koptu veya DNS çözümleme başarısız",
        max_retries=5,
        recovery_action=RecoveryAction.RETRY_WITH_DELAY,
        retry_delay_seconds=30,
        notify_user=True,
        notification_message="🌐 Ağ hatası. {retry_count}/{max_retries} yeniden bağlanılıyor...",
        is_fatal=False,
    ),
}


class ScenarioHandler:
    """
    Senaryo tespiti ve kurtarma yöneticisi.
    Agent'ın çıktısını analiz ederek hangi senaryonun gerçekleştiğini tespit eder.
    """

    def __init__(self, notifier=None):
        self.notifier = notifier
        self.retry_counts: dict[ScenarioType, int] = {}

    def detect_scenario(self, agent_output: str, error: Exception | None = None) -> ScenarioType:
        """
        Agent çıktısı veya exception'dan senaryoyu tespit et.

        Args:
            agent_output: Agent'ın text çıktısı
            error: Fırlatılan exception (varsa)

        Returns:
            Tespit edilen senaryo tipi
        """
        from src.core.exceptions import (
            AgentJoinFailed,
            AgentLoginFailed,
            AgentLinkNotFound,
            AgentMFARequired,
            AgentPageFrozen,
            CookieExpired,
            MeetingNotStarted,
        )

        # Exception-based tespit
        if error:
            if isinstance(error, AgentLoginFailed):
                return ScenarioType.DYS_LOGIN_FAIL
            elif isinstance(error, AgentLinkNotFound):
                return ScenarioType.LINK_NOT_FOUND
            elif isinstance(error, AgentMFARequired):
                mfa_type = getattr(error, "mfa_type", "sms")
                if mfa_type == "authenticator":
                    return ScenarioType.MFA_AUTHENTICATOR
                return ScenarioType.MFA_SMS
            elif isinstance(error, AgentJoinFailed):
                return ScenarioType.JOIN_FAILED
            elif isinstance(error, AgentPageFrozen):
                return ScenarioType.PAGE_FROZEN
            elif isinstance(error, CookieExpired):
                return ScenarioType.COOKIE_EXPIRED
            elif isinstance(error, MeetingNotStarted):
                return ScenarioType.MEETING_NOT_STARTED
            elif isinstance(error, (ConnectionError, TimeoutError, OSError)):
                return ScenarioType.NETWORK_ERROR

        # Text-based tespit
        output_lower = agent_output.lower() if agent_output else ""

        if "bakım" in output_lower or "maintenance" in output_lower:
            return ScenarioType.DYS_MAINTENANCE
        if "oturum sonlandırıldı" in output_lower or "kicked" in output_lower:
            return ScenarioType.SESSION_KICKED

        return ScenarioType.HAPPY_PATH

    def get_recovery(self, scenario: ScenarioType) -> ScenarioConfig:
        """Senaryo için kurtarma yapılandırmasını döndür."""
        return SCENARIO_MATRIX.get(scenario, SCENARIO_MATRIX[ScenarioType.HAPPY_PATH])

    def should_retry(self, scenario: ScenarioType) -> bool:
        """Bu senaryo için retry yapılmalı mı?"""
        config = self.get_recovery(scenario)
        current_count = self.retry_counts.get(scenario, 0)
        return current_count < config.max_retries

    def increment_retry(self, scenario: ScenarioType) -> int:
        """Retry sayacını artır ve güncel değeri döndür."""
        current = self.retry_counts.get(scenario, 0) + 1
        self.retry_counts[scenario] = current
        return current

    def reset_retries(self) -> None:
        """Tüm retry sayaçlarını sıfırla."""
        self.retry_counts.clear()

    def format_notification(
        self,
        scenario: ScenarioType,
        course_name: str = "",
    ) -> str | None:
        """Senaryo için kullanıcı bildirim mesajını formatla."""
        config = self.get_recovery(scenario)

        if not config.notify_user:
            return None

        retry_count = self.retry_counts.get(scenario, 0)

        return config.notification_message.format(
            course_name=course_name,
            retry_count=retry_count,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay_seconds,
        )

    async def execute_recovery(
        self,
        scenario: ScenarioType,
        user_id: int,
        course_name: str = "",
    ) -> RecoveryAction:
        """
        Kurtarma eylemini çalıştır.

        Returns:
            Bir sonraki adım için RecoveryAction
        """
        config = self.get_recovery(scenario)

        log.info(
            "scenario.recovery",
            scenario=scenario.value,
            action=config.recovery_action.value,
            retry_count=self.retry_counts.get(scenario, 0),
            max_retries=config.max_retries,
            is_fatal=config.is_fatal,
        )

        # Bildirim gönder
        if config.notify_user and self.notifier:
            message = self.format_notification(scenario, course_name)
            if message:
                await self.notifier.send_message(user_id=user_id, text=message)

        # Fatal ise abort
        if config.is_fatal and not self.should_retry(scenario):
            return RecoveryAction.ABORT

        # Retry kontrolü
        if config.recovery_action in (
            RecoveryAction.RETRY,
            RecoveryAction.RETRY_WITH_DELAY,
            RecoveryAction.WAIT_AND_RETRY,
        ):
            if self.should_retry(scenario):
                self.increment_retry(scenario)
                return config.recovery_action
            else:
                return RecoveryAction.ABORT

        return config.recovery_action
