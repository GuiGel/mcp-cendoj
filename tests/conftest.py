"""Shared pytest fixtures for the mcp-cendoj test suite."""

from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

import mcp_cendoj
from mcp_cendoj import app
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


@pytest.fixture
async def mcp_session(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[ClientSession]:
    """Yield an in-process MCP ClientSession connected to the mcp-cendoj server.

    Safety: sets `mcp_cendoj._client` to a sentinel object that raises AttributeError
    on any attribute access. Tests MUST override it with a real CendojClient via
    monkeypatch BEFORE calling `call_tool` — otherwise the sentinel causes an immediate
    loud failure instead of a silent real-network call to CENDOJ.
    """
    monkeypatch.setattr(mcp_cendoj, '_client', object())  # fail-loud sentinel
    async with create_connected_server_and_client_session(app) as session:
        yield session
