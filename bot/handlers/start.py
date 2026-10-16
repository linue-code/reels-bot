"""Обработчики команд /start и /help."""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot.keyboards.inline import main_menu_kb
from bot.keyboards.reply import main_reply_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    # Отправляем постоянную нижнюю клавиатуру, чтобы команды были всегда под рукой
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я — твой персональный помощник для Instagram Reels.\n\n"
        "🔗 <b>Просто отправь мне ссылку на рилс</b> — я сохраню видео на Google Drive, "
        "сделаю структурированную выжимку и прикреплю её в библиотеку.\n\n"
        "Внизу экрана появились быстрые кнопки для быстрого доступа 👇",
        reply_markup=main_reply_kb(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
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
        "4️⃣ Управление и просмотр:\n"
        "   • Нажимай кнопки внизу экрана (Библиотека, Поиск, Статистика)\n"
        "   • Под каждым рилсом есть кнопка <b>«🎬 Отправить видео в чат»</b>\n"
        "   • Или команда <code>/video номер</code> для мгновенного получения видео\n",
        reply_markup=main_reply_kb(),
    )
