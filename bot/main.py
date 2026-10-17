"""Точка входа — запуск Telegram-бота."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import TELEGRAM_BOT_TOKEN
from bot.services.database import Database
from bot.services.gdrive import GoogleDriveService
from bot.services.updater import check_restart_marker
from bot.services.logger import setup_logging
from bot.handlers import start, reels, library, admin

setup_logging()
logger = logging.getLogger(__name__)



async def main() -> None:
    # ── Инициализация сервисов ──
    db = Database()
    await db.connect()
    logger.info("База данных подключена")

    gdrive = GoogleDriveService()
    logger.info("Google Drive сервис инициализирован")

    # ── Бот и диспетчер ──
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # ── Регистрация роутеров ──
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(reels.router)
    dp.include_router(library.router)

    # ── Middleware для прокидывания зависимостей ──
    #     Все хэндлеры получат db и gdrive через **kwargs
    dp.update.middleware.register(DependencyMiddleware(db=db, gdrive=gdrive))

    # ── Настройка команд в меню Telegram (кнопка Menu слева) ──
    from aiogram.types import BotCommand

    try:
        await bot.set_my_commands([
            BotCommand(command="categories", description="📁 Категории"),
            BotCommand(command="library", description="📚 Все рилсы"),
            BotCommand(command="search", description="🔍 Поиск по выжимкам"),
            BotCommand(command="video", description="🎬 Отправить видео по номеру"),
            BotCommand(command="stats", description="📊 Статистика"),
            BotCommand(command="admin", description="⚙️ Панель администратора"),
            BotCommand(command="help", description="❓ Справка"),
        ])
    except Exception:
        pass

    # ── Проверка маркера после перезапуска / обновления ──
    asyncio.create_task(check_restart_marker(bot))

    # ── Запуск ──
    logger.info("🚀 Бот запущен!")
    try:
        await dp.start_polling(bot)

    finally:
        await db.close()
        await bot.session.close()


class DependencyMiddleware:
    """Простой middleware для прокидывания сервисов в хэндлеры."""

    def __init__(self, db: Database, gdrive: GoogleDriveService) -> None:
        self.db = db
        self.gdrive = gdrive

    async def __call__(self, handler, event, data):
        data["db"] = self.db
        data["gdrive"] = self.gdrive
        return await handler(event, data)


if __name__ == "__main__":
    asyncio.run(main())
