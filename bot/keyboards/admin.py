"""Inline-клавиатуры для админ-панели."""

from __future__ import annotations
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


POPULAR_MODELS = [
    ("gemini-3.5-flash-lite", "⭐ 3.5 Flash Lite (500 RPD, лучшая)"),
    ("gemini-3.1-flash-lite", "3.1 Flash Lite (500 RPD)"),
    ("gemini-2.5-flash", "2.5 Flash (20 RPD)"),
    ("gemini-2.0-flash", "2.0 Flash (1500 RPD)"),
    ("gemini-1.5-flash", "1.5 Flash (1500 RPD)"),
]


def admin_panel_kb() -> InlineKeyboardMarkup:
    """Главное меню панели администратора."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Сменить модель Gemini", callback_data="admin:models"),
            ],
            [
                InlineKeyboardButton(text="📜 Логи бота", callback_data="admin:logs"),
                InlineKeyboardButton(text="🔄 Обновить бота (git pull)", callback_data="admin:git_pull_confirm"),
            ],
            [
                InlineKeyboardButton(text="📋 Просмотр .env", callback_data="admin:view_env"),
                InlineKeyboardButton(text="✏️ Изменить параметр", callback_data="admin:edit_var_menu"),
            ],
            [
                InlineKeyboardButton(text="📤 Загрузить .env файлом", callback_data="admin:upload_env_prompt"),
                InlineKeyboardButton(text="📥 Скачать .env", callback_data="admin:download_env"),
            ],
            [
                InlineKeyboardButton(text="⚡ Перезапустить бота", callback_data="admin:restart_confirm"),
                InlineKeyboardButton(text="❌ Закрыть", callback_data="admin:close"),
            ],
        ]
    )


def admin_logs_kb() -> InlineKeyboardMarkup:
    """Клавиатура управления логами в Telegram."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить логи", callback_data="admin:logs_refresh"),
                InlineKeyboardButton(text="📥 Скачать bot.log", callback_data="admin:logs_download"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin:back"),
            ],
        ]
    )



def admin_models_kb(current_model: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора модели Gemini."""
    buttons = []
    for model_id, label in POPULAR_MODELS:
        prefix = "✅ " if model_id == current_model else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{prefix}{label}",
                callback_data=f"admin:set_model:{model_id}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="✍️ Ввести другую модель вручную", callback_data="admin:custom_model_prompt"),
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin:back"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_env_vars_kb() -> InlineKeyboardMarkup:
    """Быстрый выбор переменной для редактирования."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 GEMINI_MODEL", callback_data="admin:var:GEMINI_MODEL"),
                InlineKeyboardButton(text="🔑 GEMINI_API_KEY", callback_data="admin:var:GEMINI_API_KEY"),
            ],
            [
                InlineKeyboardButton(text="📢 TELEGRAM_CHANNEL_ID", callback_data="admin:var:TELEGRAM_CHANNEL_ID"),
                InlineKeyboardButton(text="📂 GOOGLE_DRIVE_FOLDER_ID", callback_data="admin:var:GOOGLE_DRIVE_FOLDER_ID"),
            ],
            [
                InlineKeyboardButton(text="👤 ADMIN_IDS", callback_data="admin:var:ADMIN_IDS"),
                InlineKeyboardButton(text="✍️ Любая другая (KEY=VAL)", callback_data="admin:var:CUSTOM"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin:back"),
            ],
        ]
    )


def admin_confirm_update_kb() -> InlineKeyboardMarkup:
    """Подтверждение запуска git pull и обновления."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Да, обновить сейчас!", callback_data="admin:do_git_pull"),
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin:back"),
            ],
        ]
    )


def admin_confirm_restart_kb() -> InlineKeyboardMarkup:
    """Подтверждение перезапуска бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Да, перезапустить!", callback_data="admin:do_restart"),
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin:back"),
            ],
        ]
    )


def admin_back_kb() -> InlineKeyboardMarkup:
    """Кнопка возврата в админку."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin:back")],
        ]
    )
