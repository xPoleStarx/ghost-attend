"""
GhostAttend — Inline Keyboard Factory

Tüm InlineKeyboardMarkup oluşturma fonksiyonları.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def onboarding_welcome_keyboard() -> InlineKeyboardMarkup:
    """Onboarding hoş geldin keyboard'u."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Kuruluma Başla 🚀", callback_data="onboard_start"),
            InlineKeyboardButton("Nasıl Çalışır? ℹ️", callback_data="onboard_info"),
        ]
    ])


def credential_type_keyboard() -> InlineKeyboardMarkup:
    """Aynı hesap mı / farklı hesaplar mı seçim keyboard'u."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Aynı hesap ✓", callback_data="cred_unified"),
            InlineKeyboardButton("Farklı hesaplar ✗", callback_data="cred_separate"),
        ]
    ])


def courses_confirm_keyboard() -> InlineKeyboardMarkup:
    """Parse edilen dersleri onaylama keyboard'u."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Tümünü Onayla ✅", callback_data="courses_confirm_all"),
            InlineKeyboardButton("Düzenle ✏️", callback_data="courses_edit"),
            InlineKeyboardButton("Baştan Al 🔄", callback_data="courses_restart"),
        ]
    ])


def session_active_keyboard() -> InlineKeyboardMarkup:
    """Aktif oturum yönetim keyboard'u."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Oturumu İptal Et ✗", callback_data="session_cancel")]
    ])


def course_select_keyboard(courses: list[dict]) -> InlineKeyboardMarkup:
    """Ders seçim keyboard'u (düzenleme için)."""
    buttons = [
        [InlineKeyboardButton(c["name"], callback_data=f"course_select_{i}")]
        for i, c in enumerate(courses)
    ]
    buttons.append([InlineKeyboardButton("Ders Ekle +", callback_data="course_add")])
    return InlineKeyboardMarkup(buttons)
