"""Сервис базы данных — SQLite с полнотекстовым поиском (FTS5)."""

from __future__ import annotations

import aiosqlite
from datetime import datetime
from dataclasses import dataclass, field
from bot.config import DB_PATH


@dataclass
class Reel:
    """Модель одного сохранённого рилса."""

    id: int | None = None
    user_id: int = 0
    instagram_url: str = ""
    author: str = ""
    original_caption: str = ""
    drive_file_id: str = ""
    drive_url: str = ""
    local_path: str = ""
    summary: str = ""
    tags: str = ""
    category: str = "Разное"
    entity_type: str = "general"  # place | movie | recipe | multi | general
    location_query: str = ""
    action_url: str = ""
    extra_data: str = "{}"
    telegram_file_id: str = ""
    status: str = "pending"  # pending | downloaded | uploaded | summarized | error
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    instagram_url   TEXT    NOT NULL DEFAULT '',
    author          TEXT    NOT NULL DEFAULT '',
    original_caption TEXT   NOT NULL DEFAULT '',
    drive_file_id   TEXT    NOT NULL DEFAULT '',
    drive_url       TEXT    NOT NULL DEFAULT '',
    local_path      TEXT    NOT NULL DEFAULT '',
    summary         TEXT    NOT NULL DEFAULT '',
    tags            TEXT    NOT NULL DEFAULT '',
    category        TEXT    NOT NULL DEFAULT 'Разное',
    entity_type     TEXT    NOT NULL DEFAULT 'general',
    location_query  TEXT    NOT NULL DEFAULT '',
    action_url      TEXT    NOT NULL DEFAULT '',
    extra_data      TEXT    NOT NULL DEFAULT '{}',
    telegram_file_id TEXT   NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'pending',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS reels_fts USING fts5(
    summary, tags, original_caption, author,
    content=reels, content_rowid=id
);

-- Триггеры для автоматической синхронизации FTS-индекса
CREATE TRIGGER IF NOT EXISTS reels_ai AFTER INSERT ON reels BEGIN
    INSERT INTO reels_fts(rowid, summary, tags, original_caption, author)
    VALUES (new.id, new.summary, new.tags, new.original_caption, new.author);
END;

CREATE TRIGGER IF NOT EXISTS reels_au AFTER UPDATE ON reels BEGIN
    INSERT INTO reels_fts(reels_fts, rowid, summary, tags, original_caption, author)
    VALUES ('delete', old.id, old.summary, old.tags, old.original_caption, old.author);
    INSERT INTO reels_fts(rowid, summary, tags, original_caption, author)
    VALUES (new.id, new.summary, new.tags, new.original_caption, new.author);
END;

CREATE TRIGGER IF NOT EXISTS reels_ad AFTER DELETE ON reels BEGIN
    INSERT INTO reels_fts(reels_fts, rowid, summary, tags, original_caption, author)
    VALUES ('delete', old.id, old.summary, old.tags, old.original_caption, old.author);
END;
"""


class Database:
    """Асинхронная обёртка над SQLite для работы с рилсами."""

    def __init__(self, path: str | None = None):
        self._path = path or str(DB_PATH)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        # Миграции для существующих баз данных
        migrations = [
            "ALTER TABLE reels ADD COLUMN telegram_file_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE reels ADD COLUMN category TEXT NOT NULL DEFAULT 'Разное'",
            "ALTER TABLE reels ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'general'",
            "ALTER TABLE reels ADD COLUMN location_query TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE reels ADD COLUMN action_url TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE reels ADD COLUMN extra_data TEXT NOT NULL DEFAULT '{}'",
        ]
        for m in migrations:
            try:
                await self._db.execute(m)
            except Exception:
                pass
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── CRUD ──────────────────────────────────────────────────

    async def add_reel(self, reel: Reel) -> int:
        """Создаёт запись и возвращает id."""
        async with self._db.execute(
            """INSERT INTO reels
               (user_id, instagram_url, author, original_caption,
                drive_file_id, drive_url, local_path, summary, tags, category,
                entity_type, location_query, action_url, extra_data,
                telegram_file_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reel.user_id,
                reel.instagram_url,
                reel.author,
                reel.original_caption,
                reel.drive_file_id,
                reel.drive_url,
                reel.local_path,
                reel.summary,
                reel.tags,
                reel.category,
                reel.entity_type,
                reel.location_query,
                reel.action_url,
                reel.extra_data,
                reel.telegram_file_id,
                reel.status,
                reel.created_at,
            ),
        ) as cursor:
            await self._db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def update_reel(self, reel_id: int, **fields) -> None:
        """Обновляет указанные поля рилса."""
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [reel_id]
        await self._db.execute(
            f"UPDATE reels SET {sets} WHERE id = ?", values
        )
        await self._db.commit()

    async def get_reel(self, reel_id: int) -> Reel | None:
        async with self._db.execute(
            "SELECT * FROM reels WHERE id = ?", (reel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_reel(row) if row else None

    async def get_reels_by_user(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> list[Reel]:
        """Последние рилсы пользователя (новые первыми)."""
        async with self._db.execute(
            """SELECT * FROM reels
               WHERE user_id = ? AND status = 'summarized'
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_reel(r) for r in rows]

    async def count_user_reels(self, user_id: int) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM reels WHERE user_id = ? AND status = 'summarized'",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def search_reels(
        self, user_id: int, query: str, limit: int = 20
    ) -> list[Reel]:
        """Полнотекстовый поиск по выжимкам, тегам и описаниям."""
        async with self._db.execute(
            """SELECT reels.* FROM reels
               JOIN reels_fts ON reels.id = reels_fts.rowid
               WHERE reels.user_id = ?
                 AND reels.status = 'summarized'
                 AND reels_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (user_id, query, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_reel(r) for r in rows]

    async def get_pending_reels(self, user_id: int) -> list[Reel]:
        """Рилсы, которые скачаны/загружены, но ещё не обработаны ИИ."""
        async with self._db.execute(
            """SELECT * FROM reels
               WHERE user_id = ? AND status IN ('pending', 'downloaded', 'uploaded')
               ORDER BY id""",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_reel(r) for r in rows]

    async def get_categories(self, user_id: int) -> list[tuple[str, int]]:
        """Возвращает список (категория, количество) для пользователя."""
        async with self._db.execute(
            """SELECT category, COUNT(*) as cnt FROM reels
               WHERE user_id = ? AND status = 'summarized' AND category != ''
               GROUP BY category ORDER BY cnt DESC, category ASC""",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [(r["category"], r["cnt"]) for r in rows]

    async def get_reels_by_category(
        self, user_id: int, category: str, limit: int = 20, offset: int = 0
    ) -> list[Reel]:
        """Возвращает рилсы выбранной категории."""
        async with self._db.execute(
            """SELECT * FROM reels
               WHERE user_id = ? AND status = 'summarized' AND category = ?
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (user_id, category, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_reel(r) for r in rows]

    async def count_reels_by_category(self, user_id: int, category: str) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM reels WHERE user_id = ? AND status = 'summarized' AND category = ?",
            (user_id, category),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def delete_reel(self, reel_id: int) -> None:
        await self._db.execute("DELETE FROM reels WHERE id = ?", (reel_id,))
        await self._db.commit()


def _row_to_reel(row: aiosqlite.Row) -> Reel:
    col_keys = row.keys()
    return Reel(
        id=row["id"],
        user_id=row["user_id"],
        instagram_url=row["instagram_url"],
        author=row["author"],
        original_caption=row["original_caption"],
        drive_file_id=row["drive_file_id"],
        drive_url=row["drive_url"],
        local_path=row["local_path"],
        summary=row["summary"],
        tags=row["tags"],
        category=row["category"] if "category" in col_keys and row["category"] else "Разное",
        entity_type=row["entity_type"] if "entity_type" in col_keys and row["entity_type"] else "general",
        location_query=row["location_query"] if "location_query" in col_keys and row["location_query"] else "",
        action_url=row["action_url"] if "action_url" in col_keys and row["action_url"] else "",
        extra_data=row["extra_data"] if "extra_data" in col_keys and row["extra_data"] else "{}",
        telegram_file_id=row["telegram_file_id"] if "telegram_file_id" in col_keys else "",
        status=row["status"],
        created_at=row["created_at"],
    )
