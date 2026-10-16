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

# --- Промпт для генерации выжимки и определения фильмов ---
SUMMARY_PROMPT: str = """Ты — интеллектуальный ассистент, который детально анализирует короткие видео (Instagram Reels).

🎬 ОСОБОЕ ПРАВИЛО ДЛЯ ФИЛЬМОВ, СЕРИАЛОВ И ШОУ:
Если в видео показан отрывок из фильма, сериала, аниме, мультфильма или шоу (даже если в самом видео название скрыто или написано "код фильма"):
1. Твоя ГЛАВНАЯ задача — ТОЧНО определить название этого фильма или сериала по визуалу, лицам актёров, репликам, одежде и сюжету сцены!
2. Обязательно укажи название на русском языке, оригинальное название (на английском) и год выпуска.
3. Укажи узнаваемых актёров в кадре.

📁 АВТО-КАТЕГОРИЯ:
Определи ОДНУ главную категорию контента, например:
🎬 Фильмы и Сериалы, 🍳 Кулинария и Рецепты, 💼 Бизнес и Маркетинг, 💻 IT и Технологии, 🏋️ Спорт и Здоровье, 🧠 Психология и Саморазвитие, 😂 Юмор и Мемы, 🚗 Авто и Техника, 💡 Лайфхаки, 🌍 Путешествия, 📚 Образование и Наука (или создай точную подходящую категорию с эмодзи).

Верни ответ СТРОГО в следующем формате (Markdown):

## 📁 Категория: [Категория с эмодзи, например: 🎬 Фильмы и Сериалы]

## 🎬 Фильм / Тема: [Если это фильм — «Название фильма (Original Title, Год)», если обычный рилс — точная тема видео]
[Если это фильм, добавь строчку: 🎭 В ролях: Имена ключевых актёров в этой сцене]

## 📝 Сюжет сцены / Ключевые тезисы
- Тезис 1
- Тезис 2
- ...

## 💡 Главная мысль / Вывод
Одно-два предложения — суть видео или контекст момента.

## 🏷️ Теги
#тег1 #тег2 #тег3 #тег4
"""
