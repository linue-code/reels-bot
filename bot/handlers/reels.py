"""Главный обработчик — приём ссылок на рилсы и полный пайплайн обработки."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.config import is_admin, TELEGRAM_CHANNEL_ID
from bot.services.database import Database, Reel
from bot.services.downloader import extract_instagram_url
from bot.services.gdrive import GoogleDriveService
from bot.services.processor import process_reel_pipeline, format_card_text_tg
from bot.keyboards.inline import reel_card_kb
from bot.keyboards.reply import main_reply_kb

logger = logging.getLogger(__name__)
router = Router()


async def safe_edit_status(
    status_msg: Message,
    text: str,
    reply_markup=None,
    disable_web_page_preview: bool = True,
) -> Message:
    """Безопасное обновление статусного сообщения с фоллбэком на отправку нового."""
    try:
        return await status_msg.edit_text(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
    except TelegramBadRequest as e:
        err_lower = str(e).lower()
        if "message is not modified" in err_lower:
            return status_msg
        logger.warning("Не удалось отредактировать статус-сообщение (%s). Отправляю новое...", e)
        try:
            return await status_msg.answer(
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception:
            return status_msg
    except Exception as e:
        logger.warning("Ошибка при редактировании статуса (%s)", e)
        try:
            return await status_msg.answer(
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception:
            return status_msg


@router.message(F.text.regexp(r"https?://(?:www\.)?instagram\.com/"))
async def handle_instagram_link(message: Message, db: Database, gdrive: GoogleDriveService) -> None:
    """
    Полный пайплайн при получении Instagram-ссылки в Telegram:
    1. Скачать видео (yt-dlp)
    2. Загрузить в Google Drive
    3. Сгенерировать выжимку (Gemini)
    4. Сохранить в базу
    5. Отправить карточку пользователю и продублировать в канал
    """
    url = extract_instagram_url(message.text or "")
    if not url:
        await message.reply("🤔 Не удалось найти ссылку на Instagram в сообщении.")
        return

    user_id = message.from_user.id
    status_msg = await message.reply(
        "⏳ <b>Обрабатываю рилс…</b>\n\n📥 Скачиваю видео…",
    )

    async def update_stage(stage: str):
        nonlocal status_msg
        if stage == "uploading_drive":
            status_msg = await safe_edit_status(status_msg, "⏳ <b>Обрабатываю рилс…</b>\n\n☁️ Загружаю в Google Drive…")
        elif stage == "analyzing_ai":
            status_msg = await safe_edit_status(status_msg, "⏳ <b>Обрабатываю рилс…</b>\n\n🤖 Генерирую выжимку (ИИ анализирует видео)…")

    result = await process_reel_pipeline(
        url=url,
        user_id=user_id,
        db=db,
        gdrive=gdrive,
        status_callback=update_stage,
    )

    if not result.success:
        await safe_edit_status(status_msg, f"❌ Ошибка при обработке рилса:\n<code>{result.error}</code>")
        return

    card_text = format_card_text_tg(result)
    card_keyboard = reel_card_kb(
        reel_id=result.reel_id,
        drive_url=result.drive_url,
        instagram_url=url,
        entity_type=result.entity_type,
        location_query=result.location_query,
        action_url=result.action_url,
    )

    await safe_edit_status(
        status_msg,
        card_text,
        reply_markup=card_keyboard,
        disable_web_page_preview=True,
    )

    # Дублируем в канал (если настроен)
    if TELEGRAM_CHANNEL_ID:
        try:
            await message.bot.send_message(
                TELEGRAM_CHANNEL_ID,
                card_text,
                reply_markup=card_keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.warning("Не удалось отправить в канал", exc_info=True)


