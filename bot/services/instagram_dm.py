"""Сервис интеграции с Instagram Direct (Instagram Messaging Graph API).

Принимает вебхуки от Meta (когда пользователь отправляет рилс в Direct),
запускает пайплайн обработки рилса и отправляет структурированный ответ
в Direct Instagram и дублирует карточку администратору в Telegram.
"""

from __future__ import annotations

import asyncio
import hmac
import hashlib
import logging
import re
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import web

from bot import config
from bot.keyboards.inline import reel_card_kb
from bot.services.database import Database
from bot.services.downloader import extract_instagram_url
from bot.services.gdrive import GoogleDriveService
from bot.services.processor import process_reel_pipeline, format_card_text_tg, format_card_text_ig

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class InstagramWebhookServer:
    """Асинхронный aiohttp веб-сервер для приёма Instagram Webhook."""

    def __init__(self, db: Database, gdrive: GoogleDriveService, bot: Bot) -> None:
        self.db = db
        self.gdrive = gdrive
        self.bot = bot
        self.app = web.Application()
        self.app.router.add_get("/webhook/instagram", self.verify_webhook)
        self.app.router.add_post("/webhook/instagram", self.handle_webhook)
        self.app.router.add_get("/health", self.health_check)
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    async def start(self) -> None:
        """Запускает веб-сервер на указанном порту."""
        port = config.INSTAGRAM_WEBHOOK_PORT
        host = config.INSTAGRAM_WEBHOOK_HOST
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        logger.info("🌐 Instagram Webhook сервер запущен на http://%s:%d/webhook/instagram", host, port)

    async def stop(self) -> None:
        """Останавливает веб-сервер."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Instagram Webhook сервер остановлен.")

    async def health_check(self, request: web.Request) -> web.Response:
        """Проверка работоспособности сервиса."""
        return web.json_response({"status": "ok", "service": "instagram-webhook"})

    async def verify_webhook(self, request: web.Request) -> web.Response:
        """
        Верификация вебхука от Meta (Facebook / Instagram):
        Meta отправляет GET-запрос с hub.mode, hub.verify_token и hub.challenge.
        """
        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        expected_token = config.INSTAGRAM_VERIFY_TOKEN
        if mode == "subscribe" and token and (token == expected_token or not expected_token):
            logger.info("✅ Успешная верификация Instagram Webhook от Meta (challenge=%s)", challenge)
            return web.Response(text=challenge or "", status=200)

        logger.warning("❌ Ошибка верификации Instagram Webhook: mode=%s, token=%s", mode, token)
        return web.Response(text="Verification token mismatch", status=403)

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        Обработка входящих событий (POST) от Meta:
        Срабатывает, когда пользователь пишет сообщение или пересылает рилс в Direct бота.
        """
        raw_body = await request.read()

        # Проверка HMAC sha256 подписи Meta (если задан INSTAGRAM_APP_SECRET)
        if config.INSTAGRAM_APP_SECRET:
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not self._verify_signature(raw_body, signature, config.INSTAGRAM_APP_SECRET):
                logger.warning("❌ Неверная HMAC-подпись входящего вебхука Instagram")
                return web.Response(text="Invalid signature", status=403)

        try:
            payload = await request.json()
        except Exception:
            return web.Response(text="Invalid JSON", status=400)

        # Meta требует быстро вернуть 200 OK (до 5 секунд), иначе вебхук будет отправлен повторно
        asyncio.create_task(self._process_payload(payload))
        return web.Response(text="EVENT_RECEIVED", status=200)

    def _verify_signature(self, raw_body: bytes, signature_header: str, secret: str) -> bool:
        if not signature_header.startswith("sha256="):
            return False
        expected_sig = signature_header[7:]
        computed_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, computed_sig)

    async def _process_payload(self, payload: dict[str, Any]) -> None:
        """Разбирает тело события Meta Graph API и ищет пересланные Reels."""
        entry_list = payload.get("entry", [])
        for entry in entry_list:
            messaging_list = entry.get("messaging", [])
            for messaging in messaging_list:
                sender_id = messaging.get("sender", {}).get("id")
                recipient_id = messaging.get("recipient", {}).get("id")
                message = messaging.get("message", {})

                # Игнорируем эхо-сообщения (когда бот сам себе отправляет ответ)
                if message.get("is_echo"):
                    continue

                if not sender_id or not message:
                    continue

                url = self._extract_url_from_ig_message(message)
                if not url:
                    logger.debug("Сообщение из Instagram DM без ссылки: %s", message)
                    continue

                logger.info("📥 Получен рилс из Instagram DM от %s: %s", sender_id, url)
                asyncio.create_task(self._handle_incoming_reel(sender_id, url))

    def _extract_url_from_ig_message(self, message: dict[str, Any]) -> str | None:
        """Извлекает URL рилса из текста, вложений или пересланного поста."""
        # 1. Обычный текст сообщения
        text = message.get("text", "")
        url = extract_instagram_url(text)
        if url:
            return url

        # 2. Вложения (attachments: share, video, ig_reel)
        attachments = message.get("attachments", [])
        for att in attachments:
            payload = att.get("payload", {})
            att_url = payload.get("url") or payload.get("reel_video_url") or ""
            extracted = extract_instagram_url(att_url)
            if extracted:
                return extracted

            # Meta часто передает url в поле share.link
            share_data = payload.get("share", {})
            if isinstance(share_data, dict):
                share_link = share_data.get("link") or ""
                extracted = extract_instagram_url(share_link)
                if extracted:
                    return extracted

        return None

    async def _handle_incoming_reel(self, ig_sender_id: str, reel_url: str) -> None:
        """Обрабатывает рилс, отправляет карточку в Instagram Direct и дублирует в Telegram."""
        # 1. Быстро подтверждаем получение в Direct
        await send_instagram_message(
            ig_sender_id,
            "⏳ Принял рилс в обработку!\nСкачиваю видео, анализирую через Gemini и сохраняю в Google Drive…",
        )

        # 2. Выполняем полный пайплайн обработки
        # Используем хэш от ig_sender_id для целочисленного user_id в базе SQLite
        synthetic_user_id = abs(hash(f"ig_{ig_sender_id}")) % 100000000

        result = await process_reel_pipeline(
            url=reel_url,
            user_id=synthetic_user_id,
            db=self.db,
            gdrive=self.gdrive,
        )

        if not result.success:
            err_msg = f"❌ Не удалось обработать рилс:\n{result.error}"
            await send_instagram_message(ig_sender_id, err_msg)
            return

        # 3. Отправляем карточку прямо в Instagram Direct
        ig_card_text = format_card_text_ig(result)
        await send_instagram_message(ig_sender_id, ig_card_text)
        logger.info("✅ Карточка успешно отправлена в Instagram Direct пользователю %s", ig_sender_id)

        # 4. Дублируем результат в Telegram
        # Отправляем в Telegram админам и/или в канал
        tg_card_text = format_card_text_tg(result)
        card_keyboard = reel_card_kb(
            reel_id=result.reel_id,
            drive_url=result.drive_url,
            instagram_url=reel_url,
            entity_type=result.entity_type,
            location_query=result.location_query,
            action_url=result.action_url,
        )

        # Дублируем администраторам в Telegram
        for admin_id in config.ADMIN_IDS:
            try:
                header = f"📸 <b>Новый рилс из Instagram Direct!</b>\nОтправитель: <code>{ig_sender_id}</code>\n\n"
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=header + tg_card_text,
                    reply_markup=card_keyboard,
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning("Не удалось отправить копию в Telegram админу %d: %s", admin_id, e)

        # Дублируем в Telegram-канал (если настроен)
        if config.TELEGRAM_CHANNEL_ID:
            try:
                await self.bot.send_message(
                    chat_id=config.TELEGRAM_CHANNEL_ID,
                    text=tg_card_text,
                    reply_markup=card_keyboard,
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning("Не удалось отправить копию в Telegram-канал: %s", e)


async def send_instagram_message(recipient_id: str, text: str) -> bool:
    """
    Отправляет текстовое сообщение в Direct Instagram через Graph API.
    Использует access_token страницы (Page Access Token) из .env.
    """
    token = config.INSTAGRAM_PAGE_ACCESS_TOKEN
    if not token:
        logger.warning("⚠️ INSTAGRAM_PAGE_ACCESS_TOKEN не задан в .env. Отправка в Direct невозможна.")
        return False

    endpoint = f"{GRAPH_API_URL}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    params = {"access_token": token}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=payload, params=params, timeout=15) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return True
                logger.error("Ошибка отправки в Instagram API (status %d): %s", resp.status, data)
                return False
    except Exception as e:
        logger.error("Исключение при вызове Instagram Send API: %s", e)
        return False
