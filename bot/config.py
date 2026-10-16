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

# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID: int | None = (
    int(os.environ["TELEGRAM_CHANNEL_ID"])
    if os.environ.get("TELEGRAM_CHANNEL_ID")
    else None
)

# --- Google Gemini ---
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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

# --- Промпт для генерации выжимки ---
SUMMARY_PROMPT: str = """Ты — ассистент, который смотрит короткие видео (Instagram Reels) и делает из них
полезную текстовую выжимку.

Проанализируй это видео и верни ответ СТРОГО в следующем формате (Markdown):

## 🎬 Тема
Одна строка — о чём этот рилс.

## 📝 Ключевые тезисы
- Тезис 1
- Тезис 2
- ...

## 💡 Главный вывод
Одно-два предложения — самая ценная мысль из видео.

## 🏷️ Теги
#тег1 #тег2 #тег3 (3-5 тегов, отражающих тему)
"""
