"""Настройка логирования бота с сохранением в файл и буфер памяти для админки."""

from __future__ import annotations

import collections
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from bot.config import BASE_DIR

LOG_FILE_PATH = BASE_DIR / "data" / "bot.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class InMemoryLogHandler(logging.Handler):
    """Хранит последние N логов в циклическом буфере памяти для мгновенного доступа в Telegram."""

    def __init__(self, capacity: int = 300):
        super().__init__()
        self.buffer: collections.deque[str] = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.buffer.append(msg)
        except Exception:
            pass

    def get_last_lines(self, n: int = 35) -> list[str]:
        return list(self.buffer)[-n:]


_memory_handler: InMemoryLogHandler | None = None


def setup_logging() -> None:
    """Инициализирует вывод логов в stdout, файл data/bot.log и кольцевой буфер памяти."""
    global _memory_handler

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Очищаем дефолтные хэндлеры во избежание дублирования
    root_logger.handlers.clear()

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Вывод в терминал (stdout) для Docker
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    # 2. Вывод в кольцевой буфер для админки Telegram
    _memory_handler = InMemoryLogHandler(capacity=300)
    _memory_handler.setFormatter(formatter)
    root_logger.addHandler(_memory_handler)

    # 3. Сохранение в файл data/bot.log (ротация до 5 МБ, 2 бэкапа)
    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=str(LOG_FILE_PATH),
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Не удалось инициализировать файл логов: {e}\n")


def get_recent_logs(lines_count: int = 35) -> str:
    """Возвращает последние N строк логов."""
    if _memory_handler and _memory_handler.buffer:
        lines = _memory_handler.get_last_lines(lines_count)
        return "\n".join(lines)

    # Fallback: читаем из файла data/bot.log
    if LOG_FILE_PATH.exists():
        try:
            content = LOG_FILE_PATH.read_text(encoding="utf-8", errors="replace")
            all_lines = content.splitlines()
            return "\n".join(all_lines[-lines_count:])
        except Exception:
            pass

    return "Логи пока пусты."
