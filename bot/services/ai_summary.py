"""Сервис генерации выжимки через Google Gemini (AI Studio)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from google import genai
from google.genai import types

from bot.config import GEMINI_API_KEY, GEMINI_MODEL, SUMMARY_PROMPT

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=GEMINI_API_KEY)


def generate_summary(video_path: Path) -> tuple[str, str]:
    """
    Загружает видео в Gemini Files API, генерирует выжимку.

    Returns:
        (summary_text, tags_string) — текст выжимки и строка с тегами.
    """
    logger.info("Загружаю видео в Gemini Files API: %s", video_path.name)

    uploaded = _client.files.upload(file=video_path)
    logger.info("Файл загружен: name=%s", uploaded.name)

    import time

    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = _client.files.get(name=uploaded.name)

    if uploaded.state.name == "FAILED":
        raise RuntimeError(f"Gemini не смог обработать видео: {uploaded.state}")

    logger.info("Генерирую выжимку через %s", GEMINI_MODEL)

    response = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_uri(
                        file_uri=uploaded.uri,
                        mime_type=uploaded.mime_type,
                    ),
                    types.Part.from_text(text=SUMMARY_PROMPT),
                ],
            )
        ],
    )

    summary_text = response.text or ""
    tags = " ".join(re.findall(r"#\w+", summary_text))

    try:
        _client.files.delete(name=uploaded.name)
    except Exception:
        pass

    logger.info("Выжимка готова (%d символов, теги: %s)", len(summary_text), tags)
    return summary_text, tags
