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
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-pro",
    ]
    seen = set()
    return [m for m in models if m and not (m in seen or seen.add(m))]


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
                response = client.models.generate_content(
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

    # 6. Извлекаем сущность (SaveToList-style) и очищаем текст
    cleaned_summary, entity_type, location_query, action_url = extract_entity_info(summary_text)

    # 7. Извлекаем категорию из текста
    category = extract_category(cleaned_summary, entity_type)

    logger.info(
        "Выжимка готова (%d симв., тип: %s, категория: %s, локация: %s)",
        len(cleaned_summary),
        entity_type,
        category,
        location_query or "нет",
    )
    return cleaned_summary, tags, category, entity_type, location_query, action_url


def extract_entity_info(summary_text: str) -> tuple[str, str, str, str]:
    """
    Извлекает entity_type, location_query, action_url из текста выжимки (SaveToList-style).
    Returns:
        (cleaned_summary, entity_type, location_query, action_url)
    """
    import json
    import urllib.parse

    entity_type = "general"
    location_query = ""
    search_title = ""

    # 1. Сначала пробуем спарсить JSON-комментарий <!--META: ...-->
    meta_match = re.search(r"<!--META:\s*({.*?})\s*-->", summary_text, re.DOTALL)
    if meta_match:
        try:
            data = json.loads(meta_match.group(1))
            entity_type = data.get("entity_type", "general").strip().lower()
            location_query = data.get("location_query", "").strip()
            search_title = data.get("search_title", "").strip()
        except Exception:
            pass

    # 2. Эвристический fallback
    if entity_type in ["general", ""] or not location_query:
        # Поиск места: "## 📍 Место: ..."
        place_match = re.search(r"📍\s*Место\s*:\s*([^\n\r]+)", summary_text)
        loc_match = re.search(r"(?:Локация|Запрос для карт)\s*:\s*([^\n\r\*]+)", summary_text)
        if place_match:
            entity_type = "place"
            p_name = place_match.group(1).strip().replace("[", "").replace("]", "")
            p_loc = loc_match.group(1).strip() if loc_match else ""
            if not location_query:
                location_query = f"{p_name}, {p_loc}".strip(", ")
            if not search_title:
                search_title = p_name

        # Поиск фильма: "## 🎬 Фильм: ..."
        movie_match = re.search(r"🎬\s*Фильм\s*:\s*([^\n\r]+)", summary_text)
        if movie_match:
            entity_type = "movie"
            if not search_title:
                search_title = movie_match.group(1).strip().replace("[", "").replace("]", "")

        # Поиск рецепта: "## 🍳 Блюдо: ..."
        recipe_match = re.search(r"🍳\s*Блюдо\s*:\s*([^\n\r]+)", summary_text)
        if recipe_match:
            entity_type = "recipe"
            if not search_title:
                search_title = recipe_match.group(1).strip().replace("[", "").replace("]", "")

        # Поиск подборки: "## 📋 Подборка: ..."
        multi_match = re.search(r"📋\s*Подборка\s*:\s*([^\n\r]+)", summary_text)
        if multi_match:
            entity_type = "multi"
            if not search_title:
                search_title = multi_match.group(1).strip().replace("[", "").replace("]", "")

    # Очищаем summary_text от META-комментария перед выводом пользователю
    cleaned_summary = re.sub(r"\n*---\n*<!--META:.*?-->", "", summary_text, flags=re.DOTALL).strip()

    # 3. Генерируем удобные action_url
    action_url = ""
    if (entity_type in ["place", "multi"] or location_query) and location_query:
        encoded_query = urllib.parse.quote(location_query)
        action_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
    elif entity_type == "movie" and search_title:
        clean_movie = re.sub(r"\(.*?\)", "", search_title).strip()
        encoded_movie = urllib.parse.quote(clean_movie or search_title)
        action_url = f"https://www.kinopoisk.ru/index.php?kp_query={encoded_movie}"

    return cleaned_summary, entity_type, location_query, action_url


def extract_category(summary_text: str, entity_type: str = "general") -> str:
    """Извлекает или определяет категорию из текста ответа модели."""
    # Поиск строки "## 📁 Категория: ..."
    match = re.search(r"📁\s*Категория\s*:\s*([^\n#\r]+)", summary_text)
    if match:
        cat = match.group(1).strip()
        cat = re.sub(r"[\*\[\]_]", "", cat).strip()
        if cat and len(cat) < 50:
            return cat

    # По типу сущности
    if entity_type == "place":
        return "📍 Места и Путешествия"
    if entity_type == "movie":
        return "🎬 Фильмы и Сериалы"
    if entity_type == "recipe":
        return "🍳 Кулинария и Рецепты"
    if entity_type == "multi":
        return "📋 Подборки и Списки"

    # Авто-определение по ключевым словам, если заголовок был утерян
    lower = summary_text.lower()
    if any(k in lower for k in ["ресторан", "кафе", "отель", "бар", "пляж", "город", "локация"]):
        return "📍 Места и Путешествия"
    if any(k in lower for k in ["фильм", "сериал", "кино", "режиссер", "в ролях", "актер"]):
        return "🎬 Фильмы и Сериалы"
    if any(k in lower for k in ["рецепт", "ингредиент", "блюдо", "варить", "жарить", "кухня", "еда"]):
        return "🍳 Кулинария и Рецепты"
    if any(k in lower for k in ["бизнес", "деньги", "продаж", "маркетинг", "инвестиц", "доход"]):
        return "💼 Бизнес и Деньги"
    if any(k in lower for k in ["код", "программирован", "нейросеть", "python", "ai", "компьютер", "технолог"]):
        return "💻 IT и Технологии"
    if any(k in lower for k in ["спорт", "тренировк", "мышц", "упражнен", "похуден"]):
        return "🏋️ Спорт и Здоровье"

    return "💡 Разное"
