from aiogram import Router, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import is_admin
from bot.keyboards.inline import main_menu_kb
from bot.keyboards.reply import main_reply_kb

router = Router()


@router.message(CommandStart(), StateFilter("*"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    # Отправляем постоянную нижнюю клавиатуру, чтобы команды были всегда под рукой
    user_is_admin = is_admin(message.from_user.id)
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я — твой персональный помощник для Instagram Reels.\n\n"
        "🔗 <b>Просто отправь мне ссылку на рилс</b> — я сохраню видео на Google Drive, "
        "сделаю структурированную выжимку и прикреплю её в библиотеку.\n\n"
        "Внизу экрана появились быстрые кнопки для быстрого доступа 👇",
        reply_markup=main_reply_kb(is_admin=user_is_admin),
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
        reply_markup=main_reply_kb(is_admin=is_admin(message.from_user.id)),
    )


@router.message(F.text.in_(["🧪 Тест", "🧪 Тест интерфейса"]))
async def cmd_test_button(message: Message) -> None:
    user_is_admin = is_admin(message.from_user.id)
    await message.answer(
        "🧪 <b>Тест успешен!</b>\n\n"
        "Интерфейс бота полностью обновлён и активен ✅\n"
        "Все кнопки работают в штатном режиме.",
        reply_markup=main_reply_kb(is_admin=user_is_admin),
    )


