"""Inline-клавиатуры для бота."""

from __future__ import annotations
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Категории", callback_data="categories")],
            [InlineKeyboardButton(text="📚 Все рилсы", callback_data="library:0")],
            [InlineKeyboardButton(text="🔍 Поиск по выжимкам", callback_data="search_prompt")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        ]
    )


def categories_kb(categories: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    """Кнопки со всеми авто-категориями и количеством рилсов."""
    buttons = []
    for cat_name, count in categories:
        buttons.append([
            InlineKeyboardButton(
                text=f"{cat_name} ({count})",
                callback_data=f"cat:{cat_name}:0",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="📚 Все рилсы подряд", callback_data="library:0"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def reel_card_kb(
    reel_id: int,
    drive_url: str,
    instagram_url: str,
    from_category: str | None = None,
    entity_type: str = "general",
    location_query: str = "",
    action_url: str = "",
) -> InlineKeyboardMarkup:
    """Кнопки под карточкой рилса с умными ссылками (SaveToList-style)."""
    import urllib.parse

    buttons = []

    # 1. Умные кнопки действий по типу сущности
    if (entity_type in ["place", "multi"] or location_query) and location_query:
        encoded = urllib.parse.quote(location_query)
        gmaps_url = action_url or f"https://www.google.com/maps/search/?api=1&query={encoded}"
        ymaps_url = f"https://yandex.ru/maps/?text={encoded}"
        buttons.append([
            InlineKeyboardButton(text="📍 Google Maps", url=gmaps_url),
            InlineKeyboardButton(text="🗺️ Яндекс Карты", url=ymaps_url),
        ])
    elif entity_type == "movie" and action_url:
        buttons.append([
            InlineKeyboardButton(text="🎬 Кинопоиск", url=action_url),
        ])

    # 2. Кнопка отправки видео в чат
    buttons.append([
        InlineKeyboardButton(text="🎬 Отправить видео в чат", callback_data=f"send_video:{reel_id}")
    ])

    # 3. Ссылки на Drive и Instagram
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

    # 4. Навигация назад и удаление
    back_cb = f"cat:{from_category}:0" if from_category else "library:0"
    back_label = f"◀️ К «{from_category}»" if from_category else "◀️ К библиотеке"

    buttons.append([
        InlineKeyboardButton(text=back_label, callback_data=back_cb),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{reel_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def library_kb(
    reels: list,
    offset: int,
    total: int,
    page_size: int = 5,
    category: str | None = None,
) -> InlineKeyboardMarkup:
    """Список рилсов с пагинацией (общий или внутри категории)."""
    buttons = []

    for reel in reels:
        label = _short_title(reel.summary, reel.id)
        cb = f"reel:{reel.id}:{category}" if category else f"reel:{reel.id}"
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=cb)]
        )

    # Навигация
    prefix = f"cat:{category}" if category else "library"
    nav = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"{prefix}:{offset - page_size}")
        )
    if offset + page_size < total:
        nav.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{prefix}:{offset + page_size}")
        )
    if nav:
        buttons.append(nav)

    bottom_row = []
    if category:
        bottom_row.append(InlineKeyboardButton(text="📁 Все категории", callback_data="categories"))
    bottom_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    buttons.append(bottom_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_library_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Категории", callback_data="categories")],
            [InlineKeyboardButton(text="◀️ Все рилсы", callback_data="library:0")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )


def _short_title(summary: str, reel_id: int) -> str:
    """Извлекает название места, фильма, блюда или тему из markdown-выжимки для кнопки."""
    for line in summary.splitlines():
        line = line.strip()
        # Место / ресторан
        if "Место:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                clean = parts[1].strip().replace("[", "").replace("]", "")
                return f"📍 #{reel_id} {clean[:45]}"
        # Фильм
        if "Фильм:" in line or ("Фильм" in line and ":" in line):
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                clean = parts[1].strip().replace("[", "").replace("]", "")
                return f"🎬 #{reel_id} {clean[:45]}"
        # Блюдо
        if "Блюдо:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                clean = parts[1].strip().replace("[", "").replace("]", "")
                return f"🍳 #{reel_id} {clean[:45]}"
        # Подборка
        if "Подборка:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                clean = parts[1].strip().replace("[", "").replace("]", "")
                return f"📋 #{reel_id} {clean[:45]}"
        # Тема
        if "Тема:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                clean = parts[1].strip().replace("[", "").replace("]", "")
                return f"#{reel_id} {clean[:45]}"

        # Иначе любая непустая строка без решетки
        if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("📁") and not line.startswith("<!--"):
            clean = line[:45]
            return f"#{reel_id} {clean}"
    return f"#{reel_id} Рилс"
