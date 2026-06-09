# src/data/cache.py
import json
import time
import aiosqlite
from pathlib import Path
from typing import Any, Optional
from src.config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
"""


class DataCache:
    def __init__(self, settings: Settings):
        self.db_path = settings.cache_db_path

    async def init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.time() + ttl
        serialized = json.dumps(value, default=str)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, serialized, expires_at),
            )
            await db.commit()

    async def get(self, key: str) -> Optional[Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                if time.time() > row["expires_at"]:
                    await db.execute("DELETE FROM cache WHERE key = ?", (key,))
                    await db.commit()
                    return None
                return json.loads(row["value"])

    async def delete(self, key: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await db.commit()
