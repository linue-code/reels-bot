"""Сервис загрузки файлов в Google Drive (поддерживает OAuth 2.0 и Service Account)."""

from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from bot.config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_CLIENT_SECRET_FILE,
    GOOGLE_TOKEN_FILE,
    GOOGLE_DRIVE_FOLDER_ID,
)

logger = logging.getLogger(__name__)

# Полный доступ к файлам, созданным приложением, и к выбранным папкам
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


def get_drive_credentials() -> Credentials:
    """
    Получает учетные данные Google Drive с поддержкой двух методов:
    1. OAuth 2.0 User Token (token.json или client_secret.json)
    2. Service Account Key (service_account.json)
    """
    token_path = Path(GOOGLE_TOKEN_FILE)
    client_secret_path = Path(GOOGLE_CLIENT_SECRET_FILE)
    service_account_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)

    # 1. Проверяем готовый OAuth 2.0 токен пользователя
    if token_path.exists():
        logger.info("Использую OAuth 2.0 токен из %s", token_path)
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            logger.info("OAuth токен истек, обновляю через refresh token...")
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    # 2. Если есть client_secret.json, но нет token.json (первичная авторизация)
    if client_secret_path.exists():
        logger.info("Найден %s. Запускаю OAuth 2.0 авторизацию...", client_secret_path)
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Токен сохранен в %s", token_path)
        return creds

    # 3. Fallback: сервисный аккаунт
    if service_account_path.exists():
        logger.info("Использую Service Account из %s", service_account_path)
        return service_account.Credentials.from_service_account_file(
            str(service_account_path), scopes=SCOPES
        )

    raise FileNotFoundError(
        "Не найдены учетные данные Google Drive! Положите client_secret.json "
        f"в {client_secret_path} (OAuth 2.0) или service_account.json в {service_account_path}"
    )


class GoogleDriveService:
    """Обёртка над Google Drive API v3."""

    def __init__(self) -> None:
        creds = get_drive_credentials()
        self._service = build("drive", "v3", credentials=creds)

    def upload_file(
        self,
        local_path: Path,
        filename: str | None = None,
        mime_type: str = "video/mp4",
        folder_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Загружает файл в Google Drive.

        Returns:
            (file_id, web_view_link) — ID файла и ссылка для просмотра.
        """
        folder = folder_id or GOOGLE_DRIVE_FOLDER_ID
        name = filename or local_path.name

        file_metadata: dict = {
            "name": name,
        }
        if folder:
            file_metadata["parents"] = [folder]

        media = MediaFileUpload(
            str(local_path),
            mimetype=mime_type,
            resumable=True,
        )

        logger.info("Загружаю в Google Drive: %s → папка %s", name, folder or "root")

        result = (
            self._service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )

        file_id: str = result["id"]
        web_link: str = result.get(
            "webViewLink", f"https://drive.google.com/file/d/{file_id}/view"
        )

        # Делаем файл доступным по ссылке (для удобного открытия из Telegram)
        try:
            self._service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()
        except Exception:
            # На некоторых корпоративных дисках запрещен общий доступ "anyone", игнорируем
            pass

        logger.info("Загружено: %s → %s", name, web_link)
        return file_id, web_link

    def download_file(self, file_id: str, destination: Path) -> Path:
        """
        Скачивает файл из Google Drive по его file_id.

        Returns:
            Path к скачанному локальному файлу.
        """
        import io
        from googleapiclient.http import MediaIoBaseDownload

        destination.parent.mkdir(parents=True, exist_ok=True)
        request = self._service.files().get_media(fileId=file_id)

        with open(destination, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(
                        "Загрузка %s: %d%%",
                        destination.name,
                        int(status.progress() * 100),
                    )

        logger.info("Файл скачан из Drive: %s", destination)
        return destination
