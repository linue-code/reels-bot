"""Постоянная нижняя клавиатура (Reply Keyboard)."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_reply_kb() -> ReplyKeyboardMarkup:
    """
    Постоянное меню внизу экрана (всегда под рукой).
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📁 Категории"),
                KeyboardButton(text="📚 Все рилсы"),
            ],
            [
                KeyboardButton(text="🔍 Поиск"),
                KeyboardButton(text="📊 Статистика"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
