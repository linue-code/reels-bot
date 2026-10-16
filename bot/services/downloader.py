"""Сервис скачивания Instagram Reels через yt-dlp."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bot.config import DOWNLOADS_DIR

logger = logging.getLogger(__name__)

INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:reel|reels|p|tv)"
    r"/[\w-]+/?(?:\?[^\s]*)?"
)


@dataclass
class DownloadResult:
    """Результат скачивания."""

    success: bool
    file_path: Path | None = None
    title: str = ""
    author: str = ""
    caption: str = ""
    duration: float = 0.0
    error: str = ""


def extract_instagram_url(text: str) -> str | None:
    """Извлекает первую Instagram-ссылку из текста сообщения."""
    match = INSTAGRAM_URL_RE.search(text)
    return match.group(0) if match else None


async def download_reel(url: str, user_id: int) -> DownloadResult:
    """
    Скачивает рилс в папку downloads/<user_id>/ и возвращает метаданные.

    Использует yt-dlp как subprocess, чтобы не блокировать event loop.
    """
    user_dir = DOWNLOADS_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(user_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--write-info-json",
        "--no-overwrites",
        "--print", "after_move:filepath",
        url,
    ]

    logger.info("Запускаю yt-dlp: %s", url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        logger.error("yt-dlp error: %s", stderr)
        return DownloadResult(success=False, error=stderr[:500])

    file_path = Path(stdout.splitlines()[-1]) if stdout else None

    if not file_path or not file_path.exists():
        mp4_files = sorted(user_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        file_path = mp4_files[-1] if mp4_files else None

    if not file_path or not file_path.exists():
        return DownloadResult(success=False, error="Файл не найден после скачивания")

    title, author, caption, duration = "", "", "", 0.0
    info_json_path = file_path.with_suffix(".info.json")
    if info_json_path.exists():
        import json

        try:
            info = json.loads(info_json_path.read_text("utf-8"))
            title = info.get("title", "")
            author = info.get("uploader", "") or info.get("channel", "")
            caption = info.get("description", "")
            duration = float(info.get("duration", 0))
        except Exception:
            logger.warning("Не удалось прочитать info.json", exc_info=True)

    logger.info("Скачано: %s (%.1f сек)", file_path.name, duration)

    return DownloadResult(
        success=True,
        file_path=file_path,
        title=title,
        author=author,
        caption=caption,
        duration=duration,
    )
