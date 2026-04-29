"""Tests for the CENDOJ async HTTP client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from mcp_cendoj.constants import (
    CENDOJ_SEARCH_URL,
    CENDOJ_SESSION_INIT_URL,
    MAX_RESPONSE_BYTES,
)
from mcp_cendoj.http import CendojClient, CendojNetworkError


@respx.mock
async def test_post_returns_text() -> None:
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    respx.post(CENDOJ_SEARCH_URL).mock(return_value=httpx.Response(200, text='result text'))

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        result = await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()

    assert result == 'result text'


@respx.mock
async def test_retry_on_429() -> None:
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    route = respx.post(CENDOJ_SEARCH_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, text='retry result'),
        ]
    )

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        result = await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()

    assert result == 'retry result'
    assert route.call_count == 2


@respx.mock
async def test_retry_on_503() -> None:
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    route = respx.post(CENDOJ_SEARCH_URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, text='retry result'),
        ]
    )

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        result = await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()

    assert result == 'retry result'
    assert route.call_count == 2


@respx.mock
async def test_timeout_raises_cendoj_network_error() -> None:
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))

    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('timeout', request=request)

    respx.post(CENDOJ_SEARCH_URL).mock(side_effect=_raise_timeout)

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        with pytest.raises(CendojNetworkError, match='timed out'):
            await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()


@respx.mock
async def test_response_too_large_raises_network_error() -> None:
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    respx.post(CENDOJ_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            content=b'small body',
            headers={'content-length': str(MAX_RESPONSE_BYTES + 1)},
        )
    )

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        with pytest.raises(CendojNetworkError, match='too large'):
            await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()
