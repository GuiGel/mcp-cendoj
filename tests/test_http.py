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


@respx.mock
async def test_close_does_not_raise() -> None:
    client = CendojClient()
    await client.close()  # should not raise


@respx.mock
async def test_session_not_reinitialised_on_second_call() -> None:
    session_route = respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    respx.post(CENDOJ_SEARCH_URL).mock(return_value=httpx.Response(200, text='result'))

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()

    assert session_route.call_count == 1  # session only initialised once


@respx.mock
async def test_get_with_content_type_returns_bytes_and_ct() -> None:
    doc_url = 'https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=123&optimize=20200615&publicinterface=true'
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    respx.get(doc_url).mock(
        return_value=httpx.Response(200, content=b'%PDF-1.4', headers={'content-type': 'application/pdf'})
    )

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        body, ct = await client.get_with_content_type(doc_url)
        await client.close()

    assert body == b'%PDF-1.4'
    assert 'pdf' in ct


@respx.mock
async def test_get_with_content_type_too_large() -> None:
    doc_url = 'https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=999&optimize=20200615&publicinterface=true'
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    respx.get(doc_url).mock(
        return_value=httpx.Response(
            200,
            content=b'x',
            headers={'content-length': str(MAX_RESPONSE_BYTES + 1), 'content-type': 'application/pdf'},
        )
    )

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        with pytest.raises(CendojNetworkError, match='too large'):
            await client.get_with_content_type(doc_url)
        await client.close()


@respx.mock
async def test_get_with_content_type_retry_on_429() -> None:
    doc_url = 'https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=777&optimize=20200615&publicinterface=true'
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))
    respx.get(doc_url).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, content=b'%PDF-1.4', headers={'content-type': 'application/pdf'}),
        ]
    )

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        body, _ct = await client.get_with_content_type(doc_url)
        await client.close()

    assert body == b'%PDF-1.4'


@respx.mock
async def test_http_error_raises_network_error() -> None:
    respx.get(CENDOJ_SESSION_INIT_URL).mock(return_value=httpx.Response(200, text='ok'))

    def _raise_http_error(request: httpx.Request) -> httpx.Response:
        raise httpx.HTTPStatusError('Bad Gateway', request=request, response=httpx.Response(502))

    respx.post(CENDOJ_SEARCH_URL).mock(side_effect=_raise_http_error)

    with patch('asyncio.sleep', new_callable=AsyncMock):
        client = CendojClient()
        with pytest.raises(CendojNetworkError, match='HTTP error'):
            await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
        await client.close()
