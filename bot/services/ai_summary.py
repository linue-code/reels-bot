"""Сервис генерации выжимки через Google Gemini (AI Studio) с авто-ретраями и fallback-моделями."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

from bot.config import GEMINI_API_KEY, GEMINI_MODEL, SUMMARY_PROMPT

logger = logging.getLogger(__name__)


def get_gemini_client() -> genai.Client:
    """Возвращает актуальный клиент Gemini с текущим API-ключом."""
    from bot import config
    return genai.Client(api_key=config.GEMINI_API_KEY)


def get_candidate_models() -> list[str]:
    """Возвращает список моделей по приоритету с учетом текущей GEMINI_MODEL."""
    from bot import config
    models = [
        config.GEMINI_MODEL,
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]
    seen = set()
    return [m for m in models if not (m in seen or seen.add(m))]


def generate_summary(video_path: Path) -> tuple[str, str, str]:
    """
    Загружает видео в Gemini Files API, генерирует выжимку.
    При ошибке 503 (перегрузка модели) делает повторную попытку и пробует запасные модели.

    Returns:
        (summary_text, tags_string, category_string) — текст выжимки, теги и авто-категория.
    """
    logger.info("Загружаю видео в Gemini Files API: %s", video_path.name)
    client = get_gemini_client()
    candidate_models = get_candidate_models()

    # 1. Загружаем файл в Gemini (хранится 48 часов, потом удаляется)
    uploaded = client.files.upload(file=video_path)
    logger.info("Файл загружен: name=%s", uploaded.name)

    # 2. Ждём, пока файл обработается
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state.name == "FAILED":
        raise RuntimeError(f"Gemini не смог обработать видео: {uploaded.state}")

    # 3. Генерируем выжимку с авто-ретраем и перебором резервных моделей
    summary_text = ""
    last_error = None

    for model_name in candidate_models:
        for attempt in range(1, 3):  # 2 попытки на модель
            try:
                logger.info("Попытка генерации через модель: %s (попытка %d)", model_name, attempt)
                response = _client.models.generate_content(
                    model=model_name,
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
                if summary_text:
                    logger.info("Выжимка успешно сгенерирована через %s", model_name)
                    break
            except Exception as e:
                err_str = str(e)
                last_error = e
                # Проверяем, является ли ошибка временной перегрузкой (503 / 429)
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "demand" in err_str.lower():
                    logger.warning(
                        "Модель %s временно перегружена (попытка %d): %s. Жду 2 сек...",
                        model_name,
                        attempt,
                        e,
                    )
                    time.sleep(2.5)
                    continue
                else:
                    # Другая ошибка — пробуем следующую модель
                    logger.warning("Ошибка при вызове модели %s: %s", model_name, e)
                    break

        if summary_text:
            break

    # 4. Удаляем временный файл из Gemini
    try:
        client.files.delete(name=uploaded.name)
    except Exception:
        pass

    if not summary_text:
        raise RuntimeError(f"Не удалось получить ответ ни от одной модели Gemini: {last_error}")

    # 5. Извлекаем теги из текста выжимки
    tags = " ".join(re.findall(r"#\w+", summary_text))

    # 6. Извлекаем категорию из текста
    category = extract_category(summary_text)

    logger.info("Выжимка готова (%d символов, категория: %s, теги: %s)", len(summary_text), category, tags)
    return summary_text, tags, category


def extract_category(summary_text: str) -> str:
    """Извлекает или определяет категорию из текста ответа модели."""
    # Поиск строки "## 📁 Категория: ..."
    match = re.search(r"📁\s*Категория\s*:\s*([^\n#\r]+)", summary_text)
    if match:
        cat = match.group(1).strip()
        cat = re.sub(r"[\*\[\]_]", "", cat).strip()
        if cat and len(cat) < 50:
            return cat

    # Авто-определение по ключевым словам, если заголовок был утерян
    lower = summary_text.lower()
    if any(k in lower for k in ["фильм", "сериал", "кино", "режиссер", "в ролях", "актер"]):
        return "🎬 Фильмы и Сериалы"
    if any(k in lower for k in ["рецепт", "ингредиент", "блюдо", "варить", "жарить", "кухня", "еда"]):
        return "🍳 Кулинария и Рецепты"
    if any(k in lower for k in ["бизнес", "деньги", "продаж", "маркетинг", "инвестиц", "доход"]):
        return "💼 Бизнес и Маркетинг"
    if any(k in lower for k in ["код", "программирован", "нейросеть", "python", "ai", "компьютер", "технолог"]):
        return "💻 IT и Технологии"
    if any(k in lower for k in ["спорт", "тренировк", "мышц", "упражнен", "похуден"]):
        return "🏋️ Спорт и Здоровье"

    return "💡 Разное"
