"""Sqlite3-backed disk cache with TTL for CENDOJ MCP server."""

import asyncio
import sqlite3
import time

import platformdirs

_DEFAULT_TTL_SECONDS = 86_400  # 24 hours


class DiskCache:
    """Thread-safe async disk cache backed by sqlite3.

    All blocking I/O is delegated to :func:`asyncio.to_thread` so event-loop
    tasks are never blocked.

    Args:
        db_path: Path to the sqlite3 database file. Defaults to the
            platform-appropriate user cache directory.
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            cache_dir = platformdirs.user_cache_path('mcp-cendoj')
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / 'cache.db')
        self._db_path = db_path
        self._initialised = False

    def _init_db(self) -> None:
        """Create table and index if they do not yet exist (called in thread)."""
        con = sqlite3.connect(self._db_path)
        try:
            con.executescript(
                'CREATE TABLE IF NOT EXISTS cache '
                '(key TEXT PRIMARY KEY, value TEXT, expires_at REAL);'
                'CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at);'
            )
            con.commit()
        finally:
            con.close()
        self._initialised = True

    async def _ensure_initialised(self) -> None:
        """Ensure the database schema has been created."""
        if not self._initialised:
            await asyncio.to_thread(self._init_db)

    def _get_sync(self, key: str) -> str | None:
        con = sqlite3.connect(self._db_path)
        try:
            row = con.execute(
                'SELECT value FROM cache WHERE key = ? AND expires_at > ?',
                (key, time.time()),
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    def _set_sync(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        con = sqlite3.connect(self._db_path)
        try:
            con.execute(
                'INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)',
                (key, value, expires_at),
            )
            con.commit()
        finally:
            con.close()

    def _clear_sync(self) -> None:
        con = sqlite3.connect(self._db_path)
        try:
            con.execute('DELETE FROM cache')
            con.commit()
        finally:
            con.close()

    async def get(self, key: str) -> str | None:
        """Return the cached value for *key*, or ``None`` if absent or expired.

        Args:
            key: Cache key (normalised to uppercase before lookup).

        Returns:
            Cached string value or ``None``.
        """
        await self._ensure_initialised()
        normalised = key.strip().upper()
        return await asyncio.to_thread(self._get_sync, normalised)

    async def set(self, key: str, value: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """Store *value* under *key* with a TTL.

        Args:
            key: Cache key (normalised to uppercase before storage).
            value: String value to cache.
            ttl_seconds: Time-to-live in seconds. Defaults to 24 hours.
        """
        await self._ensure_initialised()
        normalised = key.strip().upper()
        await asyncio.to_thread(self._set_sync, normalised, value, ttl_seconds)

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        await self._ensure_initialised()
        await asyncio.to_thread(self._clear_sync)
