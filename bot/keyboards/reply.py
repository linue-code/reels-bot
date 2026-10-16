"""Постоянная нижняя клавиатура (Reply Keyboard)."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_reply_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Постоянное меню внизу экрана (всегда под рукой).
    """
    keyboard = [
        [
            KeyboardButton(text="📁 Категории"),
            KeyboardButton(text="📚 Все рилсы"),
        ],
        [
            KeyboardButton(text="🔍 Поиск"),
            KeyboardButton(text="📊 Статистика"),
        ],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="⚙️ Админ-панель")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )

