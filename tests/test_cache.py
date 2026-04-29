"""Tests for src/mcp_cendoj/cache.py."""

import time

import pytest

from mcp_cendoj.cache import DiskCache


@pytest.fixture
def cache(tmp_path: object) -> DiskCache:
    """Isolated in-memory sqlite3 cache using a temp directory."""
    assert hasattr(tmp_path, '__truediv__'), 'tmp_path must be a Path'
    import pathlib

    p = pathlib.Path(str(tmp_path))
    return DiskCache(db_path=str(p / 'test_cache.db'))


class TestDiskCacheBasics:
    async def test_miss_returns_none(self, cache: DiskCache) -> None:
        result = await cache.get('MISSING_KEY')
        assert result is None

    async def test_set_and_get(self, cache: DiskCache) -> None:
        await cache.set('mykey', 'myvalue')
        result = await cache.get('mykey')
        assert result == 'myvalue'

    async def test_key_normalised_to_uppercase(self, cache: DiskCache) -> None:
        await cache.set('lowercase_key', 'hello')
        result = await cache.get('LOWERCASE_KEY')
        assert result == 'hello'

    async def test_key_with_spaces_normalised(self, cache: DiskCache) -> None:
        await cache.set('  spaced  ', 'value')
        result = await cache.get('SPACED')
        assert result == 'value'

    async def test_overwrite_existing(self, cache: DiskCache) -> None:
        await cache.set('k', 'v1')
        await cache.set('k', 'v2')
        result = await cache.get('k')
        assert result == 'v2'

    async def test_clear_removes_all(self, cache: DiskCache) -> None:
        await cache.set('a', '1')
        await cache.set('b', '2')
        await cache.clear()
        assert await cache.get('a') is None
        assert await cache.get('b') is None


class TestDiskCacheTTL:
    async def test_expired_entry_returns_none(self, cache: DiskCache) -> None:
        await cache.set('expiring', 'val', ttl_seconds=1)
        # Manually expire by patching expires_at
        import sqlite3

        con = sqlite3.connect(cache._db_path)  # pyright: ignore[reportPrivateUsage]
        con.execute('UPDATE cache SET expires_at = ? WHERE key = ?', (time.time() - 1, 'EXPIRING'))
        con.commit()
        con.close()
        result = await cache.get('expiring')
        assert result is None

    async def test_not_yet_expired_entry_returned(self, cache: DiskCache) -> None:
        await cache.set('fresh', 'data', ttl_seconds=3600)
        result = await cache.get('fresh')
        assert result == 'data'


class TestDiskCacheSQLInjection:
    async def test_malicious_key_stored_safely(self, cache: DiskCache) -> None:
        malicious = "' OR '1'='1"
        await cache.set(malicious, 'safe_value')
        # Should not raise; retrieval uses parameterised query
        result = await cache.get(malicious)
        assert result == 'safe_value'
