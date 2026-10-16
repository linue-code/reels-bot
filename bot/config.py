"""Конфигурация бота — загрузка переменных окружения."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Пути ---
BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "data" / "reels.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ENV_PATH = BASE_DIR / ".env"
RESTART_MARKER_PATH = BASE_DIR / "data" / "restart_marker.json"

# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID: int | None = (
    int(os.environ["TELEGRAM_CHANNEL_ID"])
    if os.environ.get("TELEGRAM_CHANNEL_ID")
    else None
)

# --- Admins ---
ADMIN_IDS_RAW: str = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()
]


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    if not ADMIN_IDS:
        # Если ADMIN_IDS пока не настроен в .env, разрешаем доступ, чтобы админ не заблокировал себя
        return True
    return user_id in ADMIN_IDS


# --- Google Gemini ---
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def reload_config() -> None:
    """Перезагружает конфигурацию из файла .env в память."""
    global GEMINI_MODEL, GEMINI_API_KEY, TELEGRAM_CHANNEL_ID, GOOGLE_DRIVE_FOLDER_ID, ADMIN_IDS, ADMIN_IDS_RAW
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    TELEGRAM_CHANNEL_ID = (
        int(os.environ["TELEGRAM_CHANNEL_ID"])
        if os.environ.get("TELEGRAM_CHANNEL_ID")
        else None
    )
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    ADMIN_IDS_RAW = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID", "")
    ADMIN_IDS = [
        int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()
    ]


# --- Google Drive ---
_sa_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/service_account.json")
_sa_path = Path(_sa_raw)
GOOGLE_SERVICE_ACCOUNT_FILE: str = str((BASE_DIR / _sa_path).resolve() if not _sa_path.is_absolute() else _sa_path)

_client_secret_raw = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "credentials/client_secret.json")
_client_secret_path = Path(_client_secret_raw)
GOOGLE_CLIENT_SECRET_FILE: str = str((BASE_DIR / _client_secret_path).resolve() if not _client_secret_path.is_absolute() else _client_secret_path)

_token_raw = os.getenv("GOOGLE_TOKEN_FILE", "credentials/token.json")
_token_path = Path(_token_raw)
GOOGLE_TOKEN_FILE: str = str((BASE_DIR / _token_path).resolve() if not _token_path.is_absolute() else _token_path)

GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

# --- Промпт для генерации выжимки и извлечения сущностей (SaveToList-style) ---
SUMMARY_PROMPT: str = """Ты — интеллектуальный ассистент и анализатор контента (SaveToList AI), который детально разбирает короткие видео (Instagram Reels).
Ты одновременно анализируешь видеоряд, надписи на видео (субтитры, вывески, чеки), голосовую дорожку и подпись к видео.

Твоя цель — извлечь суть контента в виде структурированной прикладной карточки.

Определи тип контента (entity_type):
1. 📍 PLACE (Ресторан, кафе, бар, отель, парк, достопримечательность, городская локация)
   - Укажи точное название заведения и город/страну.
   - Сформируй точный поисковый запрос для карт (например: "Trattoria da Enzo, Rome, Italy").
   - Опиши фишки, фирменные блюда/коктейли, цены, атмосферу, советы по брони.
2. 🎬 MOVIE (Фильм, сериал, мультфильм, аниме, шоу)
   - ТОЧНО определи фильм по сцене, лицам актёров, одежде и репликам (даже если в видео написано "код фильма: 123").
   - Укажи: «Название на русском (Original Title, Год)».
   - Укажи актёров в кадре, краткий сюжет сцены и смысл момента.
3. 🍳 RECIPE (Кулинарный рецепт, выпечка, напиток)
   - Название блюда.
   - Точные ингредиенты и пропорции/граммовки.
   - Пошаговые шаги приготовления и секрет идеального вкуса.
4. 📋 MULTI (Подборка / Топ N мест или фильмов, например: "5 кофеен Тбилиси", "3 фильма на вечер")
   - Оформи нумерованный список ВСЕХ упомянутых объектов (1, 2, 3...) с поисковой строкой для каждого!
5. 💡 GENERAL (Бизнес, IT, лайфхаки, психология, спорт, юмор и прочее)
   - Четкие тезисы, алгоритм действий или главная мысль.

Формат ответа (Markdown):

## 📁 Категория: [Категория с эмодзи: 📍 Места и Путешествия | 🎬 Фильмы и Сериалы | 🍳 Кулинария и Рецепты | 💼 Бизнес и Деньги | 💻 IT и Технологии | 🏋️ Спорт | 💡 Лайфхаки]

[Если это PLACE]:
## 📍 Место: [Точное название]
- **🌍 Локация:** [Город, страна / район]
- **🔍 Запрос для карт:** [Строка для Google Maps]
- **✨ Особенности и фишки:** [Что заказать, цены, бронь]

[Если это MOVIE]:
## 🎬 Фильм: [«Название (Original, Год)»]
- **🎭 В ролях:** [Имена ключевых актёров в кадре]
- **📝 Сюжет сцены:** [О чём сцена]

[Если это RECIPE]:
## 🍳 Блюдо: [Название]
- **🛒 Ингредиенты:** [Список с граммовками]
- **👨‍🍳 Приготовление:** [Ключевые шаги]

[Если это MULTI (Подборка)]:
## 📋 Подборка: [Тема подборки]
1. [Название 1] — [Город/год] — [Краткая фишка]
2. [Название 2] — [Город/год] — [Краткая фишка]

[Если это GENERAL]:
## 📌 Тема: [Главная тема]
## 📝 Ключевые тезисы
- Тезис 1
- Тезис 2

## 💡 Главный вывод / Суть
[1-2 предложения]

## 🏷️ Теги
#тег1 #тег2 #тег3 #тег4

---
<!--META: {"entity_type": "place|movie|recipe|multi|general", "location_query": "строка поиска для карт если применимо иначе пусто", "search_title": "точное название для поиска"}-->
"""

