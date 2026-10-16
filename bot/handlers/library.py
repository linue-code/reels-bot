"""Обработчики библиотеки, поиска и навигации."""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.services.database import Database
from bot.keyboards.inline import (
    main_menu_kb,
    library_kb,
    reel_card_kb,
    back_to_library_kb,
)

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


# ── Библиотека ──────────────────────────────────────────────

@router.message(Command("library"))
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

    text = f"📚 <b>Библиотека</b>  —  стр. {page}/{total_pages}  ({total} рилсов)\n\nНажми на рилс, чтобы открыть выжимку:"

    kb = library_kb(reels, offset, total, PAGE_SIZE)

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ── Просмотр конкретного рилса ──────────────────────────────

@router.callback_query(F.data.startswith("reel:"))
async def cb_view_reel(callback: CallbackQuery, db: Database) -> None:
    reel_id = int(callback.data.split(":")[1])
    reel = await db.get_reel(reel_id)

    if not reel:
        await callback.answer("Рилс не найден", show_alert=True)
        return

    author_line = f"👤 <b>{reel.author}</b>\n" if reel.author else ""
    text = f"📌 <b>Рилс #{reel.id}</b>\n{author_line}\n{reel.summary}"

    if len(text) > 4000:
        text = text[:3997] + "…"

    await callback.message.edit_text(
        text,
        reply_markup=reel_card_kb(reel.id, reel.drive_url, reel.instagram_url),
        disable_web_page_preview=True,
    )
    await callback.answer()


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
