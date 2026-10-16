import asyncio
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import DOWNLOADS_DIR, is_admin
from bot.services.database import Database, Reel
from bot.services.gdrive import GoogleDriveService
from bot.keyboards.inline import (
    main_menu_kb,
    categories_kb,
    library_kb,
    reel_card_kb,
    back_to_library_kb,
)
from bot.keyboards.reply import main_reply_kb


logger = logging.getLogger(__name__)
router = Router()
PAGE_SIZE = 5


class SearchState(StatesGroup):
    waiting_query = State()


# ── Меню ────────────────────────────────────────────────────

@router.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


# ── Категории ────────────────────────────────────────────────

@router.message(Command("categories"))
@router.message(F.text == "📁 Категории")
async def cmd_categories(message: Message, db: Database) -> None:
    await _show_categories(message, db, edit=False)


@router.callback_query(F.data == "categories")
async def cb_categories(callback: CallbackQuery, db: Database) -> None:
    await _show_categories(callback.message, db, edit=True, user_id=callback.from_user.id)
    await callback.answer()


async def _show_categories(
    message: Message, db: Database, edit: bool = False, user_id: int | None = None
) -> None:
    uid = user_id or message.from_user.id
    categories = await db.get_categories(uid)

    if not categories:
        text = "📁 <b>У вас пока нет категорий</b>\n\nОтправьте ссылку на рилс — ИИ автоматически определит категорию и создаст её!"
        if edit:
            await message.edit_text(text, reply_markup=main_menu_kb())
        else:
            await message.answer(text, reply_markup=main_menu_kb())
        return

    text = "📁 <b>Автоматические категории</b>\n\nВыберите категорию для просмотра рилсов:"
    kb = categories_kb(categories)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("cat:"))
async def cb_category_reels(callback: CallbackQuery, db: Database) -> None:
    # Формат: cat:<category_name>:<offset>
    parts = callback.data.split(":")
    category_name = parts[1]
    offset = int(parts[2]) if len(parts) > 2 else 0

    uid = callback.from_user.id
    total = await db.count_reels_by_category(uid, category_name)

    if total == 0:
        await callback.message.edit_text(
            f"📁 В категории «<b>{category_name}</b>» пока нет рилсов.",
            reply_markup=categories_kb(await db.get_categories(uid)),
        )
        await callback.answer()
        return

    reels = await db.get_reels_by_category(uid, category_name, limit=PAGE_SIZE, offset=offset)
    page = offset // PAGE_SIZE + 1
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    text = f"📁 <b>{category_name}</b> — стр. {page}/{total_pages} ({total} рилсов)\n\nНажмите на рилс, чтобы открыть:"
    kb = library_kb(reels, offset, total, PAGE_SIZE, category=category_name)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Библиотека (Все рилсы) ───────────────────────────────────

@router.message(Command("library"))
@router.message(F.text.in_(["📚 Библиотека", "📚 Все рилсы"]))
async def cmd_library(message: Message, db: Database) -> None:
    await _show_library(message, db, offset=0, edit=False)


@router.callback_query(F.data.startswith("library:"))
async def cb_library(callback: CallbackQuery, db: Database) -> None:
    offset = int(callback.data.split(":")[1])
    await _show_library(callback.message, db, offset=offset, edit=True, user_id=callback.from_user.id)
    await callback.answer()


async def _show_library(
    message: Message,
    db: Database,
    offset: int,
    edit: bool = False,
    user_id: int | None = None,
) -> None:
    uid = user_id or message.from_user.id
    total = await db.count_user_reels(uid)

    if total == 0:
        text = "📚 <b>Библиотека пуста</b>\n\nОтправь мне ссылку на Instagram Reel, чтобы начать!"
        if edit:
            await message.edit_text(text, reply_markup=main_menu_kb())
        else:
            await message.answer(text, reply_markup=main_menu_kb())
        return

    reels = await db.get_reels_by_user(uid, limit=PAGE_SIZE, offset=offset)

    page = offset // PAGE_SIZE + 1
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    text = f"📚 <b>Все рилсы</b> — стр. {page}/{total_pages} ({total} рилсов)\n\nНажми на рилс, чтобы открыть выжимку:"

    kb = library_kb(reels, offset, total, PAGE_SIZE)

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ── Просмотр конкретного рилса ──────────────────────────────

@router.callback_query(F.data.startswith("reel:"))
async def cb_view_reel(callback: CallbackQuery, db: Database) -> None:
    parts = callback.data.split(":")
    reel_id = int(parts[1])
    from_category = parts[2] if len(parts) > 2 and parts[2] != "None" else None

    reel = await db.get_reel(reel_id)

    if not reel:
        await callback.answer("Рилс не найден", show_alert=True)
        return

    author_line = f"👤 <b>{reel.author}</b>\n" if reel.author else ""
    category_line = f"📁 <b>Категория:</b> {reel.category}\n" if reel.category else ""
    text = f"📌 <b>Рилс #{reel.id}</b>\n{author_line}{category_line}\n{reel.summary}"

    if len(text) > 4000:
        text = text[:3997] + "…"

    await callback.message.edit_text(
        text,
        reply_markup=reel_card_kb(
            reel.id,
            reel.drive_url,
            reel.instagram_url,
            from_category=from_category,
            entity_type=reel.entity_type,
            location_query=reel.location_query,
            action_url=reel.action_url,
        ),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ── Отправка видео по запросу ───────────────────────────────

async def send_reel_video_to_chat(
    bot: Bot,
    chat_id: int,
    reel: Reel,
    db: Database,
    gdrive: GoogleDriveService,
    status_sender=None,
) -> None:
    """Скачивает видео из Google Drive (или берет из кэша Telegram) и отправляет в чат."""
    caption = f"🎬 <b>Рилс #{reel.id}</b>"
    if reel.author:
        caption += f" от <b>{reel.author}</b>"
    if reel.tags:
        caption += f"\n\n{reel.tags}"
    if reel.drive_url:
        caption += f"\n📂 <a href=\"{reel.drive_url}\">Открыть в Google Drive</a>"

    # 1. Если видео уже отправлялось ранее — отправляем мгновенно через telegram_file_id
    if reel.telegram_file_id:
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=reel.telegram_file_id,
                caption=caption,
                parse_mode="HTML",
            )
            return
        except Exception:
            logger.warning("Кэшированный telegram_file_id устарел, скачиваю заново из Drive...")

    # 2. Если кэша нет или он устарел — скачиваем из Google Drive
    status_msg = None
    if status_sender:
        status_msg = await status_sender("⏳ <b>Загружаю видео из Google Drive…</b>")

    temp_path = DOWNLOADS_DIR / f"temp_{reel.id}_{reel.drive_file_id}.mp4"

    try:
        await asyncio.to_thread(gdrive.download_file, reel.drive_file_id, temp_path)

        if not temp_path.exists():
            if status_msg:
                await status_msg.edit_text("❌ Не удалось получить видео из Google Drive.")
            return

        sent = await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(temp_path),
            caption=caption,
            parse_mode="HTML",
        )

        # Сохраняем telegram_file_id для будущих мгновенных отправок (без нагрузки на диск)
        if sent.video:
            await db.update_reel(reel.id, telegram_file_id=sent.video.file_id)

        if status_msg:
            await status_msg.delete()

    except Exception as e:
        logger.error("Ошибка при отправке видео: %s", e, exc_info=True)
        if status_msg:
            await status_msg.edit_text(f"❌ Ошибка при отправке видео:\n<code>{e}</code>")
    finally:
        temp_path.unlink(missing_ok=True)


@router.callback_query(F.data.startswith("send_video:"))
async def cb_send_video(
    callback: CallbackQuery, db: Database, gdrive: GoogleDriveService
) -> None:
    reel_id = int(callback.data.split(":")[1])
    reel = await db.get_reel(reel_id)

    if not reel:
        await callback.answer("Рилс не найден", show_alert=True)
        return

    await callback.answer("⏳ Загружаю видео...")
    await send_reel_video_to_chat(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        reel=reel,
        db=db,
        gdrive=gdrive,
        status_sender=callback.message.answer,
    )


@router.message(Command("video", "get"))
async def cmd_get_video(
    message: Message, db: Database, gdrive: GoogleDriveService
) -> None:
    """Команда /video <id> или /get <id> для отправки видео в чат."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "ℹ️ <b>Как получить видео:</b>\n"
            "Напишите команду с номером рилса:\n"
            "<code>/video 1</code>  или  <code>/get 1</code>\n\n"
            "<i>Номер рилса можно узнать в /library или через /search</i>"
        )
        return

    reel_id = int(parts[1].strip())
    reel = await db.get_reel(reel_id)

    if not reel or reel.user_id != message.from_user.id:
        await message.answer(f"❌ Рилс #{reel_id} не найден в вашей библиотеке.")
        return

    await send_reel_video_to_chat(
        bot=message.bot,
        chat_id=message.chat.id,
        reel=reel,
        db=db,
        gdrive=gdrive,
        status_sender=message.answer,
    )


# ── Удаление ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("delete:"))
async def cb_delete_reel(callback: CallbackQuery, db: Database) -> None:
    reel_id = int(callback.data.split(":")[1])
    await db.delete_reel(reel_id)
    await callback.message.edit_text(
        f"🗑 Рилс #{reel_id} удалён из библиотеки.",
        reply_markup=back_to_library_kb(),
    )
    await callback.answer("Удалено")


# ── Поиск ───────────────────────────────────────────────────

@router.message(F.text == "🔍 Поиск")
async def reply_search_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchState.waiting_query)
    await message.answer("🔍 Введите поисковый запрос (слово, автора или тему):")


@router.message(Command("search"))
async def cmd_search(message: Message, db: Database, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await state.set_state(SearchState.waiting_query)
        await message.answer("🔍 Введи поисковый запрос (слово или фразу):")
        return
    await _do_search(message, db, parts[1].strip())


@router.callback_query(F.data == "search_prompt")
async def cb_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchState.waiting_query)
    await callback.message.edit_text("🔍 Введи поисковый запрос (слово или фразу):")
    await callback.answer()


@router.message(SearchState.waiting_query)
async def handle_search_query(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    query = message.text.strip() if message.text else ""
    if not query:
        await message.answer("❌ Пустой запрос. Попробуй ещё раз: /search <слово>")
        return
    await _do_search(message, db, query)


async def _do_search(message: Message, db: Database, query: str) -> None:
    reels = await db.search_reels(message.from_user.id, query)

    if not reels:
        await message.answer(
            f"🔍 По запросу «<b>{query}</b>» ничего не найдено.\n\nПопробуй другие ключевые слова.",
            reply_markup=back_to_library_kb(),
        )
        return

    lines = [f"🔍 Найдено <b>{len(reels)}</b> по запросу «<b>{query}</b>»:\n"]
    for r in reels[:10]:
        # Берём первую строку темы
        title = _extract_title(r.summary)
        lines.append(f"• <b>#{r.id}</b>  {title}")

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = [
        [InlineKeyboardButton(text=f"#{r.id}  {_extract_title(r.summary)[:50]}", callback_data=f"reel:{r.id}")]
        for r in reels[:10]
    ]
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ── Статистика ──────────────────────────────────────────────

@router.message(Command("stats"))
@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message, db: Database) -> None:
    await _show_stats(message, db, edit=False)


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery, db: Database) -> None:
    await _show_stats(callback.message, db, edit=True, user_id=callback.from_user.id)
    await callback.answer()


async def _show_stats(
    message: Message, db: Database, edit: bool = False, user_id: int | None = None
) -> None:
    uid = user_id or message.from_user.id
    total = await db.count_user_reels(uid)
    pending = len(await db.get_pending_reels(uid))

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"✅ Обработано рилсов: <b>{total}</b>\n"
        f"⏳ В очереди: <b>{pending}</b>\n"
    )

    if edit:
        await message.edit_text(text, reply_markup=main_menu_kb())
    else:
        await message.answer(text, reply_markup=main_menu_kb())


# ── Утилиты ─────────────────────────────────────────────────

def _extract_title(summary: str) -> str:
    """Извлекает тему из markdown-выжимки."""
    found_header = False
    for line in summary.splitlines():
        stripped = line.strip()
        if "Тема" in stripped:
            found_header = True
            continue
        if found_header and stripped and not stripped.startswith("#"):
            return stripped[:80]
    return "Без названия"


# ── Обработчик любого текста (fallback) ────────────────────

@router.message(F.text)
async def fallback_text_handler(message: Message) -> None:
    """Отвечает на любые текстовые сообщения и прикрепляет актуальную клавиатуру."""
    user_is_admin = is_admin(message.from_user.id)
    await message.answer(
        "👋 Чтобы сохранить рилс, просто <b>отправь мне ссылку из Instagram</b>!\n\n"
        "Либо воспользуйся кнопками меню ниже 👇",
        reply_markup=main_reply_kb(is_admin=user_is_admin),
    )

