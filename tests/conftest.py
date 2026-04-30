"""Shared pytest fixtures for the mcp-cendoj test suite."""

from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from mcp_cendoj.cache import DiskCache
from mcp_cendoj.constants import CENDOJ_SEARCH_URL, CENDOJ_SESSION_INIT_URL
from mcp_cendoj.http import CendojClient


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Patch asyncio.sleep globally to eliminate delays in CendojClient retry logic.

    Uses monkeypatch (not unittest.mock.patch) for pytest-idiomatic teardown.
    Patch target 'asyncio.sleep' is correct because http.py uses `asyncio.sleep(...)`
    via the module attribute, not a local import.
    """
    monkeypatch.setattr('asyncio.sleep', AsyncMock())


@pytest.fixture
async def make_cendoj_client() -> AsyncGenerator[Callable[..., CendojClient]]:
    """Yield a factory that creates CendojClient instances backed by a respx mock transport.

    All clients created via the factory are closed when the fixture tears down.
    The factory accepts:
        html: str — response body for POST (search/lookup) requests
        session_url: str — URL to mock for session init GET (default: CENDOJ_SESSION_INIT_URL)
        post_url: str — URL to mock for POST requests (default: CENDOJ_SEARCH_URL)
        document_url: str | None — if set, a GET route returning document_bytes
        document_bytes: bytes | None — bytes to return for document_url GET route
    """
    clients: list[CendojClient] = []

    def factory(
        html: str,
        *,
        session_url: str = CENDOJ_SESSION_INIT_URL,
        post_url: str = CENDOJ_SEARCH_URL,
        document_url: str | None = None,
        document_bytes: bytes | None = None,
    ) -> CendojClient:
        router = respx.Router(assert_all_mocked=True)
        router.get(session_url).respond(200, text='ok')
        router.post(post_url).respond(200, text=html)
        if document_url is not None:
            router.get(document_url).respond(
                200,
                content=document_bytes or b'',
                headers={'Content-Type': 'application/pdf'},
            )
        transport = httpx.MockTransport(router.async_handler)
        client = CendojClient(transport=transport)
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.close()


@pytest.fixture
def disk_cache(tmp_path: Path) -> DiskCache:
    """Return an isolated DiskCache backed by a temporary directory."""
    return DiskCache(db_path=str(tmp_path / 'cache.db'))
