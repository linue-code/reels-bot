"""Сервис загрузки файлов в Google Drive через сервисный аккаунт."""

from __future__ import annotations

import logging
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from bot.config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_DRIVE_FOLDER_ID

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveService:
    """Обёртка над Google Drive API v3."""

    def __init__(self) -> None:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
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

        file_metadata = {
            "name": name,
            "parents": [folder],
        }
        media = MediaFileUpload(
            str(local_path),
            mimetype=mime_type,
            resumable=True,
        )

        logger.info("Загружаю в Google Drive: %s → папка %s", name, folder)

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
        web_link: str = result.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

        self._service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        logger.info("Загружено: %s → %s", name, web_link)
        return file_id, web_link
