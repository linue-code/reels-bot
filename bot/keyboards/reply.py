"""Постоянная нижняя клавиатура (Reply Keyboard)."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_reply_kb() -> ReplyKeyboardMarkup:
    """
    Постоянное меню внизу экрана (всегда под рукой вместо набора команд).
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📚 Библиотека"),
                KeyboardButton(text="🔍 Поиск"),
            ],
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
