"""
GhostAttend — Reply Keyboard Factory

ReplyKeyboardMarkup oluşturma fonksiyonları.
"""

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Ana menü keyboard'u (persistent reply keyboard)."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Durum"), KeyboardButton("📚 Dersler")],
            [KeyboardButton("📅 Program"), KeyboardButton("❓ Yardım")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Reply keyboard'u kaldır."""
    return ReplyKeyboardRemove()
