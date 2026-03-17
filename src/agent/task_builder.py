"""
GhostAttend — Dinamik Task String Üretimi

Agent'a verilecek görev tanımlarını (prompt) oluşturur.
İki ana akış: DYS üzerinden ders bulma ve direkt link ile katılım.
architecture.md Section 9.1
"""

from src.core.constants import (
    CHECKPOINT_COMPLETED,
    CHECKPOINT_DYS_LOGIN,
    CHECKPOINT_JOINED,
    CHECKPOINT_LINK_FOUND,
)


def build_direct_url_task(
    course_name: str,
    direct_url: str,
    end_time: str,
    mfa_code: str | None = None,
) -> str:
    """
    Direkt Teams/Zoom linki ile derse katılım görevi oluştur.
    DYS'yi atlar, doğrudan toplantı linkine gider.
    """
    mfa_hint = (
        f"\nMFA_NOTU: Eğer MFA ekranı gelirse bu kodu kullan: MFA_CODE='{mfa_code}'.\n"
        if mfa_code
        else ""
    )

    return f"""
GÖREV: {course_name} dersine katıl.

ADIM 1: {direct_url} adresine git.
ADIM 2: "Web'de devam et" veya "Web'de Katıl" seçeneğini seç.
        "Uygulamada Aç" modalı gelirse KAPAT veya "Web'de devam et"e bas.
ADIM 3: Toplantıya katıl (kamera ve mikrofon KAPALI olarak).
        - Kamera ve mikrofon toggle'larını bul ve KAPALI olduklarından emin ol.
        - "Katıl" / "Join" / "Şimdi Katıl" butonuna bas.
ADIM 4: CHECKPOINT → screenshot al, '{CHECKPOINT_JOINED}' olarak işaretle.
ADIM 5: Saat {end_time} olana kadar sayfada kal. Her 60 saniyede bir
        herhangi bir yerde ufak bir mouse hareketi yap.
        Popup veya modal gelirse KAPAT.
ADIM 6: {end_time} olduğunda CHECKPOINT → '{CHECKPOINT_COMPLETED}' olarak işaretle.

HATA DURUMU: Giriş başarısız olursa HATA_KODU: JOIN_FAILED döndür.
MFA DURUMU: SMS/authenticator kodu istenirse HATA_KODU: MFA_REQUIRED döndür.
{mfa_hint}

KRİTİK KURALLAR:
- Asla mikrofonu veya kamerayı açma.
- Teams'te "toplantıdan ayrıl" butonuna ASLA tıklama.
- Sayfa donarsa: bir kez yenile. İki kez donarsa: HATA_KODU: PAGE_FROZEN
"""


def build_dys_to_meeting_task(
    course_name: str,
    dys_url: str,
    username: str,
    password: str,
    end_time: str,
    dys_search_hint: str | None = None,
    mfa_code: str | None = None,
) -> str:
    """
    DYS üzerinden ders linki bulma ve toplantıya katılım görevi oluştur.
    Tam akış: DYS login → Ders bulma → Link tespiti → Toplantıya katılım.
    """
    search_context = (
        f"Ders adı '{dys_search_hint or course_name}' ile ara."
        if dys_search_hint
        else ""
    )

    mfa_hint = (
        f"\nMFA_NOTU: Eğer MFA/2FA kodu istenirse bu kodu kullan: MFA_CODE='{mfa_code}'.\n"
        if mfa_code
        else ""
    )

    return f"""
GÖREV: {course_name} dersine DYS üzerinden katıl.

=== AŞAMA 1: DYS GİRİŞİ ===
ADIM 1: {dys_url} adresine git.
ADIM 2: Giriş formunu bul. Kullanıcı adı/E-posta alanına '{username}' yaz.
        Şifre alanına giriş yap. "Giriş" / "Login" / "Oturum Aç" butonuna tıkla.
ADIM 3: Giriş başarılıysa CHECKPOINT → screenshot al, '{CHECKPOINT_DYS_LOGIN}' olarak işaretle.
        Başarısız → HATA_KODU: DYS_LOGIN_FAILED

=== AŞAMA 2: DERS LİNKİ BULMA ===
ADIM 4: "Derslerim", "Ders Programı", "Öğrenci Paneli", "Canlı Dersler",
        "E-Ders", "Sanal Sınıf" gibi bir bölüm veya menü öğesi bul.
ADIM 5: {course_name} dersini bul. {search_context}
ADIM 6: Dersin sayfasına gir.
ADIM 7: "Canlı Ders", "Derse Katıl", "Teams", "Zoom", "Toplantıya Katıl",
        "Join Meeting", "Sanal Sınıfa Gir", "Online Ders" gibi bir link veya buton ara.
        Ders duyurularına, mesajlara ve detay sayfasına da bak.
        Bulunamadı → HATA_KODU: LINK_NOT_FOUND
ADIM 8: Linki bulduysan CHECKPOINT → screenshot al, '{CHECKPOINT_LINK_FOUND}' olarak işaretle.

=== AŞAMA 3: DERSE KATILMA ===
ADIM 9: Linke tıkla.
ADIM 10: Teams/Zoom web arayüzü açıldıysa:
         - "Uygulamada Aç" modalı → KAPAT veya "Web'de devam et"e tıkla
         - Kamera/mikrofon izin isterlerse REDDET
         - Kamera ve mikrofon toggle'larını bul ve KAPALI olduklarından emin ol
         - "Katıl" / "Join" / "Şimdi Katıl" butonuna bas
ADIM 11: Derse girildikten sonra CHECKPOINT → screenshot al, '{CHECKPOINT_JOINED}' olarak işaretle.

=== AŞAMA 4: DERSE DEVAM ===
ADIM 12: Saat {end_time} olana kadar sayfada kal.
         Her 45–90 saniyede bir sayfada küçük bir mouse hareketi yap.
         Herhangi bir popup/modal gelirse KAPAT.
ADIM 13: {end_time}'da CHECKPOINT → '{CHECKPOINT_COMPLETED}' olarak işaretle.

KRİTİK KURALLAR:
- Asla mikrofonu veya kamerayı açma.
- MFA/2FA kodu istenirse hemen dur: HATA_KODU: MFA_REQUIRED
{mfa_hint}
- Sayfa donarsa: bir kez yenile. İki kez donarsa: HATA_KODU: PAGE_FROZEN
- Teams'te "toplantıdan ayrıl" butonuna ASLA tıklama.
- "Oturumu kapat" / "Logout" butonlarına ASLA tıklama.
"""


def build_cookie_login_task(
    course_name: str,
    dys_url: str,
    end_time: str,
    dys_search_hint: str | None = None,
    mfa_code: str | None = None,
) -> str:
    """
    Kayıtlı cookie'ler ile DYS'ye giriş (şifre gerektirmez).
    Cookie'ler context'e önceden yüklenmiş olmalı.
    """
    search_context = (
        f"Ders adı '{dys_search_hint or course_name}' ile ara."
        if dys_search_hint
        else ""
    )

    mfa_hint = (
        f"\nMFA_NOTU: Eğer MFA/2FA kodu istenirse bu kodu kullan: MFA_CODE='{mfa_code}'.\n"
        if mfa_code
        else ""
    )

    return f"""
GÖREV: {course_name} dersine kayıtlı oturum ile katıl.

ADIM 1: {dys_url} adresine git.
        Eğer zaten giriş yapılmışsa (dashboard/panel görünüyorsa) devam et.
        Eğer login sayfasına yönlendirildiysen → HATA_KODU: COOKIE_EXPIRED
ADIM 2: CHECKPOINT → screenshot al, '{CHECKPOINT_DYS_LOGIN}' olarak işaretle.
ADIM 3: "{course_name}" dersini bul. {search_context}
ADIM 4: Canlı ders linkini bul.
        Bulunamadı → HATA_KODU: LINK_NOT_FOUND
ADIM 5: CHECKPOINT → screenshot al, '{CHECKPOINT_LINK_FOUND}' olarak işaretle.
ADIM 6: Linke tıkla ve toplantıya katıl (kamera/mikrofon KAPALI).
ADIM 7: CHECKPOINT → screenshot al, '{CHECKPOINT_JOINED}' olarak işaretle.
ADIM 8: Saat {end_time}'a kadar bekle, her 60sn mouse hareketi yap.
ADIM 9: {end_time}'da CHECKPOINT → '{CHECKPOINT_COMPLETED}'.

KRİTİK: Kamera/mikrofon AÇMA. MFA istenirse HATA_KODU: MFA_REQUIRED.
{mfa_hint}
"""
