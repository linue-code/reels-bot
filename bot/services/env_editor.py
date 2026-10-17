"""Сервис для безопасного чтения, редактирования и обновления файла .env."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from bot.config import ENV_PATH, reload_config

logger = logging.getLogger(__name__)

# Секретные ключи, которые нужно маскировать при выводе
SECRET_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "GEMINI_API_KEY",
    "INSTAGRAM_PAGE_ACCESS_TOKEN",
    "INSTAGRAM_APP_SECRET",
}


def read_env_raw(env_path: Path = ENV_PATH) -> str:
    """Возвращает содержимое .env файла как текст."""
    if not env_path.exists():
        return ""
    try:
        return env_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Ошибка при чтении .env: %s", e)
        return ""


def mask_secret(value: str) -> str:
    """Маскирует секретное значение (показывает первые 6 и последние 4 символа)."""
    val = value.strip().strip("'\"")
    if len(val) <= 10:
        return "********"
    return f"{val[:6]}...{val[-4:]}"


def get_masked_env_text(env_path: Path = ENV_PATH) -> str:
    """Возвращает содержимое .env с замаскированными API-ключами."""
    raw = read_env_raw(env_path)
    if not raw:
        return "# Файл .env пуст или отсутствует"

    output_lines = []
    for line in raw.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            output_lines.append(line)
            continue

        if "=" in line:
            key, val = line.split("=", 1)
            key_name = key.strip()
            if key_name in SECRET_KEYS:
                output_lines.append(f"{key_name}={mask_secret(val)}")
            else:
                output_lines.append(line)
        else:
            output_lines.append(line)

    return "\n".join(output_lines)


def set_env_variable(key: str, value: str, env_path: Path = ENV_PATH) -> bool:
    """
    Устанавливает или заменяет переменную в .env файле.
    Также сразу обновляет os.environ и вызывает reload_config().
    """
    try:
        # Если значение содержит пробелы или переводы строк — экранируем
        val_str = str(value).strip()
        if "\n" in val_str or " " in val_str:
            formatted_val = f'"{val_str}"'
        else:
            formatted_val = val_str

        if not env_path.exists():
            env_path.write_text(f"{key}={formatted_val}\n", encoding="utf-8")
        else:
            raw = env_path.read_text(encoding="utf-8")
            lines = raw.splitlines()
            found = False
            new_lines = []

            for line in lines:
                stripped = line.strip()
                if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                    new_lines.append(f"{key}={formatted_val}")
                    found = True
                else:
                    new_lines.append(line)

            if not found:
                new_lines.append(f"{key}={formatted_val}")

            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # Обновляем переменные окружения процесса
        os.environ[key] = val_str
        reload_config()
        logger.info("Успешно обновлена переменная .env: %s", key)
        return True
    except Exception as e:
        logger.error("Не удалось записать в .env: %s", e)
        return False


def save_new_env(new_content: str, env_path: Path = ENV_PATH) -> tuple[bool, str]:
    """
    Сохраняет новый контент .env с созданием резервной копии .env.bak.
    """
    try:
        # Проверяем, что в файле хотя бы есть знак '='
        lines = [line.strip() for line in new_content.splitlines() if line.strip() and not line.startswith("#")]
        if not any("=" in line for line in lines):
            return False, "Неверный формат: файл не содержит переменных в виде KEY=VALUE"

        # Создаем резервную копию
        if env_path.exists():
            backup_path = env_path.with_suffix(".env.bak")
            shutil.copyfile(env_path, backup_path)

        # Записываем новый файл
        env_path.write_text(new_content.strip() + "\n", encoding="utf-8")
        reload_config()
        return True, "Файл .env успешно сохранён!"
    except Exception as e:
        logger.error("Ошибка при сохранении нового .env: %s", e)
        return False, str(e)
