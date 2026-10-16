"""Сервис автоматического обновления бота (git pull) и мягкого перезапуска."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from aiogram import Bot
from bot.config import BASE_DIR, RESTART_MARKER_PATH, GEMINI_MODEL
from bot.keyboards.reply import main_reply_kb

logger = logging.getLogger(__name__)


async def git_pull_updates() -> tuple[bool, str, str]:
    """
    Выполняет git pull в директории проекта.
    Returns:
        (success, message, commit_details)
    """
    git_bin = shutil.which("git")
    if not git_bin:
        return False, "❌ Git не установлен в системе/контейнере.", ""

    # Настраиваем safe.directory для избежания ошибок прав в Docker
    try:
        subprocess.run(
            [git_bin, "config", "--global", "--add", "safe.directory", "*"],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass

    try:
        # 1. Проверяем наличие удаленного репозитория
        proc_fetch = await asyncio.to_thread(
            subprocess.run,
            [git_bin, "fetch", "origin", "main"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc_fetch.returncode != 0:
            err = proc_fetch.stderr.strip() or proc_fetch.stdout.strip()
            return False, f"❌ Ошибка git fetch:\n<code>{err}</code>", ""

        # 2. Получаем список новых коммитов
        proc_log = await asyncio.to_thread(
            subprocess.run,
            [git_bin, "log", "HEAD..origin/main", "--oneline"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        new_commits = proc_log.stdout.strip()

        # 3. Выполняем git pull
        proc_pull = await asyncio.to_thread(
            subprocess.run,
            [git_bin, "pull", "origin", "main"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc_pull.returncode != 0:
            err = proc_pull.stderr.strip() or proc_pull.stdout.strip()
            return False, f"❌ Ошибка git pull:\n<code>{err}</code>", ""

        pull_output = proc_pull.stdout.strip()
        if "Already up to date" in pull_output or "Уже обновлено" in pull_output:
            return True, "👌 Бот уже обновлён до последней версии!", ""

        return True, "✅ Обновления успешно скачаны!", new_commits or pull_output

    except Exception as e:
        logger.error("Исключение при обновлении через git: %s", e, exc_info=True)
        return False, f"❌ Ошибка при выполнении обновления: <code>{e}</code>", ""


async def schedule_restart(chat_id: int, message_id: int | None = None, is_update: bool = False) -> None:
    """
    Записывает маркер перезапуска и через 1 секунду перезапускает процесс Python.
    """
    try:
        marker = {
            "chat_id": chat_id,
            "message_id": message_id,
            "is_update": is_update,
            "timestamp": time.time(),
        }
        RESTART_MARKER_PATH.write_text(json.dumps(marker), encoding="utf-8")
    except Exception as e:
        logger.error("Не удалось записать restart_marker.json: %s", e)

    # Небольшая задержка для завершения отправки сообщения Telegram
    await asyncio.sleep(1.0)

    logger.info("⚡ Запуск os.execv для перезагрузки процесса бота...")
    # os.execv заменяет текущий процесс на новый
    os.execv(sys.executable, [sys.executable, "-m", "bot.main"])


async def check_restart_marker(bot: Bot) -> None:
    """
    Проверяет файл маркера перезапуска при старте бота и отправляет отчет админу.
    """
    await asyncio.sleep(1.5)  # Небольшая пауза, чтобы бот точно был готов отправлять сообщения
    if not RESTART_MARKER_PATH.exists():
        return

    try:
        content = RESTART_MARKER_PATH.read_text(encoding="utf-8")
        RESTART_MARKER_PATH.unlink(missing_ok=True)
        marker = json.loads(content)

        chat_id = marker.get("chat_id")
        is_update = marker.get("is_update", False)

        from bot import config
        title = "🔄 <b>Бот успешно обновлён и перезапущен!</b>" if is_update else "⚡ <b>Бот успешно перезапущен!</b>"
        text = (
            f"✅ {title}\n\n"
            f"🤖 Активная модель: <code>{config.GEMINI_MODEL}</code>\n"
            f"🚀 Бот работает в штатном режиме."
        )

        if chat_id:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=main_reply_kb(is_admin=True),
            )
    except Exception as e:
        logger.error("Ошибка при проверке маркера перезапуска: %s", e)
