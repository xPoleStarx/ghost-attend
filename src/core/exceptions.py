"""
GhostAttend — Exception Hiyerarşisi

Tüm proje geneli exception'lar burada tanımlıdır.
Her exception tipi, ilgili hata senaryosuna (Senaryo Matrisi) karşılık gelir.
"""


class GhostAttendError(Exception):
    """Base exception for all GhostAttend errors."""
    pass


# ── Agent Hataları ──

class AgentError(GhostAttendError):
    """Base exception for web agent errors."""
    pass


class AgentLoginFailed(AgentError):
    """DYS login başarısız. Yanlış credential veya hesap kilitli."""
    pass


class AgentLinkNotFound(AgentError):
    """DYS'de ders linki bulunamadı."""
    pass


class AgentMFARequired(AgentError):
    """MFA doğrulaması gerekiyor (SMS, Authenticator, vb.)."""

    def __init__(self, mfa_type: str = "unknown", message: str = "MFA required"):
        self.mfa_type = mfa_type  # 'sms' | 'authenticator' | 'email'
        super().__init__(message)


class AgentJoinFailed(AgentError):
    """Derse katılım başarısız (Teams/Zoom giriş hatası)."""
    pass


class AgentPageFrozen(AgentError):
    """Sayfa dondu veya agent timeout'a uğradı."""
    pass


class AgentMaxRetryExceeded(AgentError):
    """Maksimum retry sayısına ulaşıldı."""

    def __init__(self, retry_count: int = 3, message: str = "Max retry exceeded"):
        self.retry_count = retry_count
        super().__init__(message)


class MeetingNotStarted(AgentError):
    """Toplantı henüz başlatılmamış (hoca başlatmamış)."""
    pass


# ── Credential Hataları ──

class CredentialError(GhostAttendError):
    """Base exception for credential-related errors."""
    pass


class CredentialNotFound(CredentialError):
    """Kullanıcı için credential bulunamadı."""
    pass


class CredentialDecryptFailed(CredentialError):
    """Credential çözümleme başarısız (master key değişmiş olabilir)."""
    pass


class CookieExpired(CredentialError):
    """Session cookie süresi dolmuş, yeniden giriş gerekiyor."""
    pass


# ── Vision Hataları ──

class VisionError(GhostAttendError):
    """Base exception for vision/LLM parsing errors."""
    pass


class ScheduleParseError(VisionError):
    """Ders programı parse edilemedi (JSON geçersiz, görsel okunamadı)."""
    pass


class LowConfidenceParseError(VisionError):
    """Bazı dersler düşük güven skoru ile parse edildi."""

    def __init__(self, low_confidence_courses: list, message: str = "Low confidence courses detected"):
        self.courses = low_confidence_courses
        super().__init__(message)


# ── Scheduler Hataları ──

class SchedulerError(GhostAttendError):
    """Base exception for scheduler errors."""
    pass


class JobAlreadyExists(SchedulerError):
    """Aynı ders için zaten bir scheduled job var."""
    pass
