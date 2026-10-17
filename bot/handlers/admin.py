"""Обработчики панели администратора: смена моделей, редактирование .env, git pull и перезапуск."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, FSInputFile

from bot import config
from bot.config import is_admin, reload_config, ENV_PATH
from bot.keyboards.admin import (
    admin_panel_kb,
    admin_logs_kb,
    admin_models_kb,
    admin_env_vars_kb,
    admin_confirm_update_kb,
    admin_confirm_restart_kb,
    admin_back_kb,
)
from bot.keyboards.reply import main_reply_kb
from bot.services.database import Database
from bot.services.logger import get_recent_logs, LOG_FILE_PATH
from bot.services.env_editor import (
    get_masked_env_text,
    read_env_raw,
    set_env_variable,
    save_new_env,
    mask_secret,
)
from bot.services.updater import git_pull_updates, schedule_restart

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    waiting_custom_model = State()
    waiting_var_value = State()
    waiting_env_file = State()


def _get_admin_dashboard_text(user_id: int) -> str:
    """Генерирует сводный текст статуса системы для админа."""
    masked_gemini_key = mask_secret(config.GEMINI_API_KEY) if config.GEMINI_API_KEY else "❌ Не задан"
    channel_status = f"<code>{config.TELEGRAM_CHANNEL_ID}</code>" if config.TELEGRAM_CHANNEL_ID else "⚪ Выключен"
    drive_folder = f"<code>{config.GOOGLE_DRIVE_FOLDER_ID}</code>" if config.GOOGLE_DRIVE_FOLDER_ID else "Корневая папка"
    admins_str = ", ".join(str(a) for a in config.ADMIN_IDS) if config.ADMIN_IDS else f"Все (ваш ID: <code>{user_id}</code>)"

    ig_status = "🟢 Включён" if config.INSTAGRAM_ENABLE_WEBHOOK else "⚪ Выключен"
    ig_token_status = "✅ Задан" if config.INSTAGRAM_PAGE_ACCESS_TOKEN else "⚠️ Не настроен токен"
    ig_info = f"{ig_status} ({ig_token_status})"

    return (
        "⚙️ <b>Панель администратора</b>\n\n"
        f"🤖 <b>Модель Gemini:</b> <code>{config.GEMINI_MODEL}</code>\n"
        f"🔑 <b>API-ключ Gemini:</b> <code>{masked_gemini_key}</code>\n"
        f"📸 <b>Instagram DM Webhook:</b> {ig_info}\n"
        f"📢 <b>Telegram-канал:</b> {channel_status}\n"
        f"📂 <b>Папка Drive:</b> {drive_folder}\n"
        f"👤 <b>Администраторы:</b> {admins_str}\n\n"
        "Выберите действие ниже:"
    )


# ── Вход в админ-панель ──────────────────────────────────────

@router.message(Command("admin"))
@router.message(F.text == "⚙️ Админ-панель")
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id
    if not is_admin(uid):
        await message.answer("⛔ У вас нет доступа к панели администратора.")
        return

    text = _get_admin_dashboard_text(uid)
    await message.answer(text, reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin:back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    uid = callback.from_user.id
    if not is_admin(uid):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    text = _get_admin_dashboard_text(uid)
    await callback.message.edit_text(text, reply_markup=admin_panel_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("⚙️ Панель администратора закрыта.")
    await callback.answer()


# ── Выбор модели Gemini ──────────────────────────────────────

@router.callback_query(F.data == "admin:models")
async def cb_admin_models(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    text = (
        "🤖 <b>Выбор модели Google Gemini</b>\n\n"
        f"Текущая модель: <code>{config.GEMINI_MODEL}</code>\n\n"
        "📊 <b>Лимиты бесплатного тарифа (AI Studio):</b>\n"
        "• <b>3.5 Flash Lite:</b> 500 RPD (15 RPM) — ⭐️ <i>рекомендуется</i>\n"
        "• <b>3.1 Flash Lite:</b> 500 RPD (15 RPM)\n"
        "• <b>3.8 Flash:</b> 20 RPD (5 RPM) — <i>новейшая флагманская</i>\n"
        "• <b>3.6 Flash:</b> 20 RPD (5 RPM)\n"
        "• <b>2.5 Flash:</b> 20 RPD (5 RPM)\n"
        "• <b>2.5 Flash Lite:</b> 20 RPD (10 RPM)\n\n"
        "<i>💡 Для постоянной работы рекомендуется <b>3.5 Flash Lite</b> (до 500 рилсов в день бесплатно).</i>"
    )
    await callback.message.edit_text(text, reply_markup=admin_models_kb(config.GEMINI_MODEL))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set_model:"))
async def cb_admin_set_model(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    new_model = callback.data.split(":", 2)[2]
    set_env_variable("GEMINI_MODEL", new_model)
    config.GEMINI_MODEL = new_model

    await callback.answer(f"✅ Модель переключена на {new_model}!", show_alert=True)

    text = (
        "🤖 <b>Выбор модели Google Gemini</b>\n\n"
        f"Текущая модель: <code>{config.GEMINI_MODEL}</code>\n\n"
        "✅ <b>Модель успешно сохранена в .env и активирована!</b>\n\n"
        "📊 <b>Лимиты бесплатного тарифа (AI Studio):</b>\n"
        "• <b>3.5 Flash Lite:</b> 500 RPD (15 RPM) — ⭐️ <i>рекомендуется</i>\n"
        "• <b>3.1 Flash Lite:</b> 500 RPD (15 RPM)\n"
        "• <b>3.8 Flash:</b> 20 RPD (5 RPM) — <i>новейшая</i>\n"
        "• <b>3.6 Flash:</b> 20 RPD (5 RPM)\n"
        "• <b>2.5 Flash:</b> 20 RPD (5 RPM)\n"
        "• <b>2.5 Flash Lite:</b> 20 RPD (10 RPM)"
    )
    await callback.message.edit_text(text, reply_markup=admin_models_kb(config.GEMINI_MODEL))


@router.callback_query(F.data == "admin:custom_model_prompt")
async def cb_admin_custom_model_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_custom_model)
    await callback.message.edit_text(
        "✍️ <b>Введите точное название модели:</b>\n\n"
        "Например: <code>gemini-3.5-flash-lite</code> или <code>gemini-3.8-flash</code>\n\n"
        "Или отправьте /cancel для отмены.",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_custom_model)
async def handle_custom_model_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    if message.text in ["/cancel", "Отмена"]:
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_panel_kb())
        return

    model_name = message.text.strip()
    set_env_variable("GEMINI_MODEL", model_name)
    config.GEMINI_MODEL = model_name
    await state.clear()

    await message.answer(
        f"✅ <b>Модель успешно изменена на:</b> <code>{model_name}</code>\n"
        f"Значение сохранено в .env и применяется для всех новых рилсов.",
        reply_markup=admin_panel_kb(),
    )


# ── Просмотр логов ───────────────────────────────────────────

@router.callback_query(F.data == "admin:logs")
async def cb_admin_logs(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    logs = get_recent_logs(lines_count=30)
    if len(logs) > 3800:
        logs = logs[-3800:]

    text = f"📜 <b>Последние логи бота:</b>\n\n<pre>{logs}</pre>"
    await callback.message.edit_text(text, reply_markup=admin_logs_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:logs_refresh")
async def cb_admin_logs_refresh(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    logs = get_recent_logs(lines_count=30)
    if len(logs) > 3800:
        logs = logs[-3800:]

    text = f"📜 <b>Последние логи бота (обновлено):</b>\n\n<pre>{logs}</pre>"
    try:
        await callback.message.edit_text(text, reply_markup=admin_logs_kb())
    except Exception:
        pass
    await callback.answer("Логи обновлены 🔄")


@router.callback_query(F.data == "admin:logs_download")
async def cb_admin_logs_download(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    if not LOG_FILE_PATH.exists():
        await callback.answer("Файл логов пока не создан", show_alert=True)
        return

    await callback.answer("Отправляю файл логов...")
    await callback.message.answer_document(
        FSInputFile(LOG_FILE_PATH, filename="bot.log"),
        caption="📄 <b>Полный файл логов бота</b>",
    )


# ── Просмотр и редактирование .env ───────────────────────────

@router.callback_query(F.data == "admin:view_env")
async def cb_admin_view_env(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    text_env = get_masked_env_text()
    if len(text_env) > 3800:
        text_env = text_env[:3750] + "\n... (слишком длинный)"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁️ Показать без маскировки", callback_data="admin:view_env_full")],
        [InlineKeyboardButton(text="📥 Скачать .env файлом", callback_data="admin:download_env")],
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin:back")],
    ])

    await callback.message.edit_text(
        f"📋 <b>Текущий файл .env:</b>\n\n<pre>{text_env}</pre>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "admin:view_env_full")
async def cb_admin_view_env_full(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    raw = read_env_raw()
    if len(raw) > 3800:
        raw = raw[:3750] + "\n... (файл сокращен)"

    await callback.message.edit_text(
        f"⚠️ <b>Файл .env (без маскировки):</b>\n\n<pre>{raw}</pre>",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:download_env")
async def cb_admin_download_env(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    if not ENV_PATH.exists():
        await callback.answer("❌ Файл .env не найден", show_alert=True)
        return

    await callback.answer("Отправляю файл...")
    await callback.message.answer_document(
        FSInputFile(ENV_PATH, filename=".env"),
        caption="📄 <b>Ваш файл .env</b>",
    )


@router.callback_query(F.data == "admin:upload_env_prompt")
async def cb_admin_upload_env_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_env_file)
    await callback.message.edit_text(
        "📤 <b>Загрузка нового файла .env</b>\n\n"
        "Отправьте файл <code>.env</code> прямо в этот чат как документ.\n"
        "Бот автоматически сделает резервную копию старого файла (.env.bak) и обновит настройки.\n\n"
        "Отправьте /cancel для отмены.",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_env_file, F.document)
async def handle_env_file_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    doc = message.document
    if not doc:
        return

    file_info = await bot.get_file(doc.file_id)
    dest_path = config.DOWNLOADS_DIR / f"new_env_{message.from_user.id}.tmp"

    try:
        await bot.download_file(file_info.file_path, destination=dest_path)
        content = dest_path.read_text(encoding="utf-8")
        success, res_msg = save_new_env(content)

        if success:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚡ Перезапустить бота сейчас", callback_data="admin:do_restart")],
                [InlineKeyboardButton(text="◀️ В главное меню админки", callback_data="admin:back")],
            ])
            await message.answer(
                "✅ <b>Файл .env успешно обновлён и сохранён!</b>\n\n"
                "Рекомендуется перезапустить бота, чтобы все сервисы применили новые параметры.",
                reply_markup=kb,
            )
        else:
            await message.answer(f"❌ Ошибка валидации: {res_msg}", reply_markup=admin_panel_kb())
    except Exception as e:
        logger.error("Ошибка при сохранении загруженного .env: %s", e)
        await message.answer(f"❌ Ошибка при обработке файла: {e}", reply_markup=admin_panel_kb())
    finally:
        dest_path.unlink(missing_ok=True)
        await state.clear()


@router.callback_query(F.data == "admin:edit_var_menu")
async def cb_admin_edit_var_menu(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text(
        "✏️ <b>Выберите параметр для изменения:</b>",
        reply_markup=admin_env_vars_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:var:"))
async def cb_admin_choose_var(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    var_name = callback.data.split(":", 2)[2]
    await state.update_data(target_var=var_name)
    await state.set_state(AdminStates.waiting_var_value)

    if var_name == "CUSTOM":
        prompt = (
            "✍️ <b>Введите имя и значение переменной в формате:</b>\n"
            "<code>KEY=VALUE</code>\n\n"
            "Например: <code>SOME_KEY=12345</code>"
        )
    else:
        current_val = getattr(config, var_name, "")
        prompt = (
            f"✍️ <b>Введите новое значение для переменной <code>{var_name}</code>:</b>\n\n"
            f"Текущее значение: <code>{current_val}</code>\n\n"
            "Отправьте /cancel для отмены."
        )

    await callback.message.edit_text(prompt, reply_markup=admin_back_kb())
    await callback.answer()


@router.message(AdminStates.waiting_var_value)
async def handle_var_value_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    if message.text in ["/cancel", "Отмена"]:
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_panel_kb())
        return

    data = await state.get_data()
    target_var = data.get("target_var", "CUSTOM")
    user_input = message.text.strip()

    if target_var == "CUSTOM":
        if "=" not in user_input:
            await message.answer("❌ Неверный формат. Нужно: <code>KEY=VALUE</code>. Попробуйте еще раз:")
            return
        key, val = user_input.split("=", 1)
        key = key.strip()
        val = val.strip()
    else:
        key = target_var
        val = user_input

    set_env_variable(key, val)
    await state.clear()

    await message.answer(
        f"✅ Переменная <code>{key}</code> успешно обновлена на:\n<code>{val}</code>",
        reply_markup=admin_panel_kb(),
    )


# ── Автоматическое обновление через git pull ─────────────────

@router.callback_query(F.data == "admin:git_pull_confirm")
async def cb_admin_git_pull_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    text = (
        "🔄 <b>Обновление бота через Git</b>\n\n"
        "Бот выполнит <code>git pull origin main</code> из GitHub-репозитория.\n"
        "Если есть свежие коммиты, бот автоматически перезапустится с новым кодом.\n\n"
        "Запустить обновление?"
    )
    await callback.message.edit_text(text, reply_markup=admin_confirm_update_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:do_git_pull")
async def cb_admin_do_git_pull(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text(
        "⏳ <b>Проверяю и скачиваю обновления с GitHub…</b>\n\nПожалуйста, подождите несколько секунд.",
    )
    await callback.answer("Запускаю git pull...")

    success, msg, details = await git_pull_updates()

    if not success:
        await callback.message.edit_text(
            f"{msg}\n\nПопробуйте обновить вручную через SSH или проверьте доступ.",
            reply_markup=admin_back_kb(),
        )
        return

    if "Already up to date" in msg or "уже обновлён" in msg:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Всё равно перезапустить", callback_data="admin:do_restart")],
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin:back")],
        ])
        await callback.message.edit_text(
            "👌 <b>Бот уже обновлён до последней версии!</b>\n\nНовых коммитов в репозитории нет.",
            reply_markup=kb,
        )
        return

    # Новые коммиты получены! Перезапускаем!
    await callback.message.edit_text(
        f"📥 <b>Получены новые обновления:</b>\n\n"
        f"<code>{details[:1000]}</code>\n\n"
        "⚡ <b>Перезапускаю бота для применения нового кода…</b>",
    )

    # Запускаем перезапуск процесса
    await schedule_restart(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        is_update=True,
    )


# ── Перезапуск бота ──────────────────────────────────────────

@router.callback_query(F.data == "admin:restart_confirm")
async def cb_admin_restart_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text(
        "⚡ <b>Перезапуск бота</b>\n\n"
        "Процесс бота будет мягко перезапущен. Все активные настройки из .env применятся.\n\n"
        "Перезапустить сейчас?",
        reply_markup=admin_confirm_restart_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:do_restart")
async def cb_admin_do_restart(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text("⚡ <b>Перезапускаю бота…</b>\nЧерез секунду он будет снова онлайн.")
    await callback.answer("Перезапуск...")

    await schedule_restart(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        is_update=False,
    )
