"""Inline-клавиатуры для бота."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Моя библиотека", callback_data="library:0")],
            [InlineKeyboardButton(text="🔍 Поиск по выжимкам", callback_data="search_prompt")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        ]
    )


def reel_card_kb(reel_id: int, drive_url: str, instagram_url: str) -> InlineKeyboardMarkup:
    """Кнопки под карточкой рилса."""
    buttons = [
        [InlineKeyboardButton(text="🎬 Отправить видео в чат", callback_data=f"send_video:{reel_id}")],
    ]
    links_row = []
    if drive_url:
        links_row.append(
            InlineKeyboardButton(text="📂 Google Drive", url=drive_url)
        )
    if instagram_url:
        links_row.append(
            InlineKeyboardButton(text="📱 Instagram", url=instagram_url)
        )
    if links_row:
        buttons.append(links_row)

    buttons.append([
        InlineKeyboardButton(text="◀️ К библиотеке", callback_data="library:0"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{reel_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def library_kb(
    reels: list, offset: int, total: int, page_size: int = 5
) -> InlineKeyboardMarkup:
    """Список рилсов с пагинацией."""
    buttons = []

    for reel in reels:
        label = _short_title(reel.summary, reel.id)
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"reel:{reel.id}")]
        )

    nav = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"library:{offset - page_size}")
        )
    if offset + page_size < total:
        nav.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"library:{offset + page_size}")
        )
    if nav:
        buttons.append(nav)

    buttons.append(
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_library_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К библиотеке", callback_data="library:0")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )


def _short_title(summary: str, reel_id: int) -> str:
    """Извлекает тему из markdown-выжимки для отображения в кнопке."""
    for line in summary.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            title = line[:60]
            if len(line) > 60:
                title += "…"
            return f"#{reel_id}  {title}"
    return f"#{reel_id}  Рилс"
