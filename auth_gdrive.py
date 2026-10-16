#!/usr/bin/env python3
"""
Скрипт первичной OAuth 2.0 авторизации в Google Drive.

Запустите:
    python auth_gdrive.py

Скрипт откроет браузер, попросит вас войти в свой Google-аккаунт и предоставить доступ
к Google Диску. После этого будет создан файл `credentials/token.json`, который
содержит постоянный токен доступа (refresh token).
"""

from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

CLIENT_SECRET_FILE = Path("credentials/client_secret.json")
TOKEN_FILE = Path("credentials/token.json")


def main():
    print("=" * 60)
    print("🔐 Авторизация Google Drive (OAuth 2.0)")
    print("=" * 60)

    if not CLIENT_SECRET_FILE.exists():
        print(f"\n❌ Ошибка: Файл {CLIENT_SECRET_FILE} не найден!")
        print("\nЧто нужно сделать:")
        print("1. Зайдите в Google Cloud Console -> APIs & Services -> Credentials")
        print("2. Создайте 'OAuth 2.0 Client ID' (тип: Desktop app)")
        print("3. Скачайте JSON-файл и сохраните как credentials/client_secret.json")
        return

    print(f"\n1. Читаю {CLIENT_SECRET_FILE}...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)

    print("2. Открываю браузер для входа в Google-аккаунт...")
    print("   (Если браузер не открылся сам, скопируйте ссылку из консоли)")
    try:
        creds = flow.run_local_server(port=0)
    except Exception as e:
        print(f"\nНе удалось запустить локальный сервер: {e}")
        print("Пробую альтернативный режим консоли...")
        creds = flow.run_console()

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    print(f"\n✅ Успешно! Токен сохранён в: {TOKEN_FILE}")

    # Проверяем доступ к API
    service = build("drive", "v3", credentials=creds)
    about = service.about().get(fields="user").execute()
    user = about.get("user", {})
    print(f"👤 Авторизован как: {user.get('displayName')} ({user.get('emailAddress')})")
    print("\n🎉 Настройка Google Drive завершена! Теперь бот готов к запуску.")


if __name__ == "__main__":
    main()
