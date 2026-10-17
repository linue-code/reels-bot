"""Унифицированный сервис обработки рилса и генерации карточки.

Используется совместно Telegram-обработчиком и вебхуком Instagram DM.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.services.database import Database, Reel
from bot.services.downloader import download_reel, DownloadResult
from bot.services.gdrive import GoogleDriveService
from bot.services.ai_summary import generate_summary

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


@dataclass
class ProcessReelResult:
    """Результат выполнения пайплайна обработки рилса."""
    success: bool
    reel_id: int | None = None
    reel: Reel | None = None
    author: str = ""
    summary: str = ""
    tags: str = ""
    category: str = "Разное"
    entity_type: str = "general"
    location_query: str = ""
    action_url: str = ""
    drive_url: str = ""
    error: str = ""


async def process_reel_pipeline(
    url: str,
    user_id: int,
    db: Database,
    gdrive: GoogleDriveService,
    status_callback: Any | None = None,
) -> ProcessReelResult:
    """
    Выполняет полный пайплайн:
    1. Запись в БД со статусом pending
    2. Скачивание видео (yt-dlp)
    3. Загрузка в Google Drive
    4. Генерация выжимки и классификация через Gemini (AI Studio)
    5. Обновление записи в БД и очистка локального файла
    """
    # 1. Создаём запись в базе
    reel = Reel(user_id=user_id, instagram_url=url, status="pending")
    reel_id = await db.add_reel(reel)
    reel.id = reel_id

    # Вспомогательный коллбек для прогресса
    async def update_status(stage: str):
        if status_callback and callable(status_callback):
            try:
                res = status_callback(stage)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.debug("Коллбек статуса вернул ошибку: %s", e)

    await update_status("downloading")

    # 2. Скачиваем
    try:
        download_res: DownloadResult = await download_reel(url, user_id)
    except Exception as e:
        logger.error("Ошибка скачивания: %s", e, exc_info=True)
        await db.update_reel(reel_id, status="error")
        return ProcessReelResult(success=False, reel_id=reel_id, error=f"Ошибка скачивания: {e}")

    if not download_res.success or not download_res.file_path:
        await db.update_reel(reel_id, status="error")
        return ProcessReelResult(success=False, reel_id=reel_id, error=download_res.error or "Не удалось скачать видео")

    await db.update_reel(
        reel_id,
        status="downloaded",
        author=download_res.author,
        original_caption=download_res.caption,
        local_path=str(download_res.file_path),
    )

    # 3. Загружаем в Google Drive
    await update_status("uploading_drive")
    drive_file_id = ""
    drive_url = ""
    try:
        drive_file_id, drive_url = await asyncio.to_thread(
            gdrive.upload_file,
            download_res.file_path,
            f"{download_res.author}_{download_res.file_path.stem}.mp4" if download_res.author else None,
        )
    except Exception as e:
        logger.error("Ошибка загрузки в Drive: %s", e, exc_info=True)
        await db.update_reel(reel_id, status="error")
        return ProcessReelResult(success=False, reel_id=reel_id, error=f"Ошибка загрузки в Google Drive: {e}")

    await db.update_reel(
        reel_id,
        status="uploaded",
        drive_file_id=drive_file_id,
        drive_url=drive_url,
    )

    # 4. Генерируем выжимку через Gemini
    await update_status("analyzing_ai")
    summary = ""
    tags = ""
    category = "Разное"
    entity_type = "general"
    location_query = ""
    action_url = ""

    try:
        summary, tags, category, entity_type, location_query, action_url = await asyncio.to_thread(
            generate_summary, download_res.file_path
        )
    except Exception as e:
        logger.error("Ошибка генерации выжимки: %s", e, exc_info=True)
        await db.update_reel(reel_id, status="uploaded")
        # Рилс уже в Drive, но без выжимки
        return ProcessReelResult(
            success=True,
            reel_id=reel_id,
            author=download_res.author,
            drive_url=drive_url,
            summary=f"⚠️ Видео сохранено в Google Drive, но ИИ не смог сгенерировать выжимку.\nОшибка: {e}",
            error=str(e),
        )

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

    # 5. Очищаем локальные файлы
    try:
        download_res.file_path.unlink(missing_ok=True)
        info_json = download_res.file_path.with_suffix(".info.json")
        info_json.unlink(missing_ok=True)
    except Exception:
        pass

    return ProcessReelResult(
        success=True,
        reel_id=reel_id,
        author=download_res.author,
        summary=summary,
        tags=tags,
        category=category,
        entity_type=entity_type,
        location_query=location_query,
        action_url=action_url,
        drive_url=drive_url,
    )


def format_card_text_tg(result: ProcessReelResult) -> str:
    """Форматирует текст карточки для отправки в Telegram (HTML)."""
    author_line = f"👤 <b>{result.author}</b>\n" if result.author else ""
    card_text = (
        f"✅ <b>Рилс сохранён!</b>  (#{result.reel_id})\n\n"
        f"{author_line}"
        f"{result.summary}"
    )
    if len(card_text) > 4000:
        card_text = card_text[:3997] + "…"
    return card_text


def format_card_text_ig(result: ProcessReelResult) -> str:
    """Форматирует текст карточки для отправки в Instagram DM (чистый текст без HTML)."""
    import re

    # Убираем HTML-теги для Instagram Direct
    clean_summary = re.sub(r"<[^>]+>", "", result.summary)
    # Заменяем Markdown заголовки на более компактный вид
    clean_summary = re.sub(r"##\s*", "", clean_summary)

    lines = [
        f"✅ Рилс сохранён в коллекцию! (#{result.reel_id})",
    ]
    if result.author:
        lines.append(f"Автор: @{result.author}")
    lines.append("")
    lines.append(clean_summary)
    lines.append("")
    lines.append(f"☁️ Google Drive: {result.drive_url}")
    if result.action_url:
        lines.append(f"📍 Открыть: {result.action_url}")

    ig_text = "\n".join(lines).strip()
    if len(ig_text) > 950:
        ig_text = ig_text[:947] + "…"
    return ig_text
