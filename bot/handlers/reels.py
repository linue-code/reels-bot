"""Главный обработчик — приём ссылок на рилсы и полный пайплайн обработки."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.config import is_admin
from bot.services.database import Database, Reel
from bot.services.downloader import extract_instagram_url, download_reel
from bot.services.gdrive import GoogleDriveService
from bot.services.ai_summary import generate_summary
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
    Полный пайплайн при получении Instagram-ссылки:
    1. Скачать видео (yt-dlp)
    2. Загрузить в Google Drive
    3. Сгенерировать выжимку (Gemini)
    4. Сохранить в базу
    5. Отправить карточку пользователю
    """
    url = extract_instagram_url(message.text or "")
    if not url:
        await message.reply("🤔 Не удалось найти ссылку на Instagram в сообщении.")
        return

    user_id = message.from_user.id
    status_msg = await message.reply(
        "⏳ <b>Обрабатываю рилс…</b>\n\n📥 Скачиваю видео…",
    )

    # ── 1. Создаём запись в базе ──
    reel = Reel(user_id=user_id, instagram_url=url, status="pending")
    reel_id = await db.add_reel(reel)

    # ── 2. Скачиваем ──
    try:
        result = await download_reel(url, user_id)
    except Exception as e:
        logger.error("Ошибка скачивания: %s", e, exc_info=True)
        await db.update_reel(reel_id, status="error")
        status_msg = await safe_edit_status(status_msg, f"❌ Ошибка скачивания:\n<code>{e}</code>")
        return

    if not result.success:
        await db.update_reel(reel_id, status="error")
        status_msg = await safe_edit_status(status_msg, f"❌ Не удалось скачать:\n<code>{result.error}</code>")
        return

    await db.update_reel(
        reel_id,
        status="downloaded",
        author=result.author,
        original_caption=result.caption,
        local_path=str(result.file_path),
    )

    # ── 3. Загружаем в Google Drive ──
    status_msg = await safe_edit_status(status_msg, "⏳ <b>Обрабатываю рилс…</b>\n\n☁️ Загружаю в Google Drive…")

    try:
        drive_file_id, drive_url = await asyncio.to_thread(
            gdrive.upload_file,
            result.file_path,
            f"{result.author}_{result.file_path.stem}.mp4" if result.author else None,
        )
    except Exception as e:
        logger.error("Ошибка загрузки в Drive: %s", e, exc_info=True)
        await db.update_reel(reel_id, status="error")
        status_msg = await safe_edit_status(status_msg, f"❌ Ошибка загрузки в Drive:\n<code>{e}</code>")
        return

    await db.update_reel(
        reel_id,
        status="uploaded",
        drive_file_id=drive_file_id,
        drive_url=drive_url,
    )

    # ── 4. Генерируем выжимку ──
    status_msg = await safe_edit_status(status_msg, "⏳ <b>Обрабатываю рилс…</b>\n\n🤖 Генерирую выжимку (ИИ анализирует видео)…")

    try:
        summary, tags, category, entity_type, location_query, action_url = await asyncio.to_thread(
            generate_summary, result.file_path
        )
    except Exception as e:
        logger.error("Ошибка генерации выжимки: %s", e, exc_info=True)
        # Даже если ИИ не смог — рилс уже в Drive, сохраняем как есть
        await db.update_reel(reel_id, status="uploaded")
        status_msg = await safe_edit_status(
            status_msg,
            f"⚠️ Видео сохранено в Google Drive, но выжимку не удалось сгенерировать.\n\n"
            f"<code>{e}</code>\n\n"
            f"📂 <a href=\"{drive_url}\">Открыть в Drive</a>",
        )
        return

    await db.update_reel(
        reel_id,
        status="summarized",
        summary=summary,
        tags=tags,
        category=category,
        entity_type=entity_type,
        location_query=location_query,
        action_url=action_url,
    )

    # ── 5. Удаляем локальный файл (экономим место) ──
    try:
        result.file_path.unlink(missing_ok=True)
        # Удаляем и .info.json
        info_json = result.file_path.with_suffix(".info.json")
        info_json.unlink(missing_ok=True)
    except Exception:
        pass

    # ── 6. Отправляем красивую карточку ──
    author_line = f"👤 <b>{result.author}</b>\n" if result.author else ""

    card_text = (
        f"✅ <b>Рилс сохранён!</b>  (#{reel_id})\n\n"
        f"{author_line}"
        f"{summary}"
    )

    # Telegram ограничивает длину сообщения 4096 символами
    if len(card_text) > 4000:
        card_text = card_text[:3997] + "…"

    card_keyboard = reel_card_kb(
        reel_id,
        drive_url,
        url,
        entity_type=entity_type,
        location_query=location_query,
        action_url=action_url,
    )

    status_msg = await safe_edit_status(
        status_msg,
        card_text,
        reply_markup=card_keyboard,
        disable_web_page_preview=True,
    )

    # ── 7. Дублируем в канал (опционально) ──
    from bot.config import TELEGRAM_CHANNEL_ID

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

