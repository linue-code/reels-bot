"""Обработчики команд /start и /help."""

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot.keyboards.inline import main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я — твой персональный помощник для Instagram Reels.\n\n"
        "🔗 <b>Отправь мне ссылку на рилс</b> — я скачаю видео, "
        "загружу его в Google Drive и сделаю краткую выжимку с помощью ИИ.\n\n"
        "Все твои сохранённые рилсы и выжимки доступны в библиотеке 📚\n\n"
        "<b>Команды:</b>\n"
        "/library — 📚 библиотека сохранённых рилсов\n"
        "/search <i>запрос</i> — 🔍 поиск по выжимкам\n"
        "/stats — 📊 статистика\n"
        "/help — ❓ справка",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "❓ <b>Как пользоваться ботом</b>\n\n"
        "1️⃣ Скопируй ссылку на рилс в Instagram\n"
        "   (Поделиться → Скопировать ссылку)\n\n"
        "2️⃣ Отправь ссылку мне в чат\n\n"
        "3️⃣ Я автоматически:\n"
        "   • 📥 Скачаю видео\n"
        "   • ☁️ Загружу в Google Drive\n"
        "   • 🤖 Сделаю текстовую выжимку (ИИ)\n"
        "   • 💾 Сохраню всё в библиотеку\n\n"
        "4️⃣ Ищи свои конспекты:\n"
        "   /library — просмотр всех рилсов\n"
        "   /search рецепт — поиск по ключевым словам\n",
    )
