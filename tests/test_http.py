"""Tests for the CENDOJ async HTTP client."""

import asyncio

import httpx
import pytest
import respx

from mcp_cendoj.constants import (
    CENDOJ_SEARCH_URL,
    CENDOJ_SESSION_INIT_URL,
    MAX_RESPONSE_BYTES,
)
from mcp_cendoj.http import CendojClient, CendojNetworkError


async def test_post_returns_text() -> None:
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).respond(200, text='result text')
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    result = await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()

    assert result == 'result text'


async def test_retry_on_429() -> None:
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    route = router.post(CENDOJ_SEARCH_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, text='retry result')]
    )
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    result = await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()

    assert result == 'retry result'
    assert route.call_count == 2


async def test_retry_on_503() -> None:
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    route = router.post(CENDOJ_SEARCH_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text='retry result')]
    )
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    result = await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()

    assert result == 'retry result'
    assert route.call_count == 2


async def test_timeout_raises_cendoj_network_error() -> None:
    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('timeout', request=request)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_raise_timeout)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError, match='timed out'):
        await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()


async def test_response_too_large_raises_network_error() -> None:
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).respond(
        200,
        content=b'small body',
        headers={'content-length': str(MAX_RESPONSE_BYTES + 1)},
    )
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError, match='too large'):
        await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()


async def test_close_does_not_raise() -> None:
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))
    await client.close()  # should not raise


async def test_session_not_reinitialised_on_second_call() -> None:
    router = respx.Router(assert_all_mocked=True)
    session_route = router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).respond(200, text='result')
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()

    assert session_route.call_count == 1  # session only initialised once


async def test_session_cookie_forwarded_to_post() -> None:
    """Verify the session cookie set by GET is forwarded to the POST request."""
    received_cookies: list[str] = []

    def _capture_post(request: httpx.Request) -> httpx.Response:
        cookie_header = request.headers.get('cookie', '')
        received_cookies.append(cookie_header)
        return httpx.Response(200, text='ok')

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok', headers={'Set-Cookie': 'JSESSIONID=test-abc; Path=/'})
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_capture_post)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()

    assert any('JSESSIONID=test-abc' in c for c in received_cookies), (
        f'Expected JSESSIONID cookie in POST, got: {received_cookies}'
    )


async def test_get_with_content_type_returns_bytes_and_ct() -> None:
    doc_url = 'https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=123&optimize=20200615&publicinterface=true'
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.get(doc_url).respond(200, content=b'%PDF-1.4', headers={'content-type': 'application/pdf'})
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    body, ct = await client.get_with_content_type(doc_url)
    await client.close()

    assert body == b'%PDF-1.4'
    assert 'pdf' in ct


async def test_get_with_content_type_too_large() -> None:
    doc_url = 'https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=999&optimize=20200615&publicinterface=true'
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.get(doc_url).respond(
        200,
        content=b'x',
        headers={'content-length': str(MAX_RESPONSE_BYTES + 1), 'content-type': 'application/pdf'},
    )
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError, match='too large'):
        await client.get_with_content_type(doc_url)
    await client.close()


async def test_get_with_content_type_retry_on_429() -> None:
    doc_url = 'https://www.poderjudicial.es/search/contenidos.action?action=contentpdf&databasematch=TS&reference=777&optimize=20200615&publicinterface=true'
    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.get(doc_url).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, content=b'%PDF-1.4', headers={'content-type': 'application/pdf'}),
        ]
    )
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    body, _ct = await client.get_with_content_type(doc_url)
    await client.close()

    assert body == b'%PDF-1.4'


async def test_http_error_raises_network_error() -> None:
    def _raise_http_error(request: httpx.Request) -> httpx.Response:
        raise httpx.HTTPStatusError('Bad Gateway', request=request, response=httpx.Response(502))

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_raise_http_error)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError, match='HTTP error'):
        await client.post(CENDOJ_SEARCH_URL, data={'action': 'query'})
    await client.close()


async def test_no_sleep_fixture_actually_patches() -> None:
    """Smoke test: verify the _no_sleep autouse fixture is active."""
    import time

    start = time.perf_counter()
    await asyncio.sleep(10.0)  # must be instant due to _no_sleep autouse fixture
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f'_no_sleep not working: sleep(10) took {elapsed:.3f}s'
