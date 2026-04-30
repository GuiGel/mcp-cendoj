"""CENDOJ async HTTP client with rate limiting, retry, and session management."""

import asyncio
import random
from typing import Any

import httpx

from mcp_cendoj.constants import (
    CENDOJ_SESSION_INIT_URL,
    CONNECT_TIMEOUT_S,
    DEFAULT_HEADERS,
    MAX_RESPONSE_BYTES,
    RATE_LIMIT_RPS,
    READ_TIMEOUT_S,
)


class CendojNetworkError(Exception):
    """Raised on unrecoverable HTTP errors from the CENDOJ endpoint."""


class CendojClient:
    """Async HTTP client for CENDOJ with rate limiting and session management.

    Manages the JSESSIONID session cookie automatically: the first call to
    :meth:`post` or :meth:`get` triggers a GET to CENDOJ_SESSION_INIT_URL,
    which causes the server to set the HttpOnly cookie.

    Rate limiting is per-process: concurrent Claude Desktop sessions (multiple
    processes) each have their own semaphore and are not serialised across
    process boundaries. Do not use this client for high-concurrency workloads.
    """

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Initialise the client with a persistent async httpx session.

        Args:
            transport: Optional custom transport for testing (e.g. httpx.MockTransport).
                       When None, httpx uses its default network transport.
        """
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT_S,
            read=READ_TIMEOUT_S,
            write=10.0,
            pool=5.0,
        )
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._semaphore = asyncio.Semaphore(RATE_LIMIT_RPS)
        self._session_initialised = False

    async def _ensure_session(self) -> None:
        """GET the CENDOJ search page to acquire a JSESSIONID session cookie.

        The server sets an HttpOnly cookie that must be present on every
        subsequent POST. httpx stores and resends it automatically via its
        internal cookie jar. This method is idempotent: it only fires the
        initial GET once per client instance.
        """
        if not self._session_initialised:
            await self._client.get(CENDOJ_SESSION_INIT_URL)
            self._session_initialised = True

    async def post(self, url: str, data: dict[str, Any]) -> str:
        """POST form data to url with rate limiting and retry.

        Args:
            url: The endpoint URL.
            data: URL-encoded form fields.

        Returns:
            Response body as a string.

        Raises:
            CendojNetworkError: On HTTP errors, timeouts, or oversized responses.
        """
        await self._ensure_session()
        return await self._request_with_retry('POST', url, data=data)

    async def get(self, url: str) -> tuple[str, str]:
        """GET a URL with rate limiting and retry, returning the body as text.

        Note:
            The returned content_type string is always ``''``. Use
            :meth:`get_with_content_type` when the MIME type matters
            (e.g. to detect PDF responses).

        Args:
            url: The endpoint URL.

        Returns:
            Tuple of ``(response_body_text, content_type)`` where
            ``content_type`` is always an empty string.

        Raises:
            CendojNetworkError: On HTTP errors, timeouts, or oversized responses.
        """
        await self._ensure_session()
        body = await self._request_with_retry('GET', url)
        return body, ''

    async def get_with_content_type(self, url: str) -> tuple[bytes, str]:
        """GET a URL and return the raw response bytes together with its MIME type.

        Use this method — rather than :meth:`get` — when the caller needs to
        distinguish between PDF and HTML responses (e.g. the document endpoint).

        Args:
            url: The endpoint URL.

        Returns:
            Tuple of ``(raw_bytes, content_type)`` where ``content_type`` is the
            value of the ``Content-Type`` response header (e.g.
            ``'application/pdf'``), or an empty string if the header is absent.

        Raises:
            CendojNetworkError: On HTTP errors, timeouts, or oversized responses.
        """
        await self._ensure_session()
        async with self._semaphore:
            await asyncio.sleep(1.0 / RATE_LIMIT_RPS)
            for attempt in range(3):
                try:
                    resp = await self._client.get(url)
                    if resp.status_code == 403:
                        raise CendojNetworkError(
                            'CENDOJ returned 403 — IP temporarily blocked by WAF. Wait 15–60 minutes before retrying.'
                        )
                    if resp.status_code == 500:
                        raise CendojNetworkError(
                            'CENDOJ returned 500 — the requested resource may not exist or the query is invalid.'
                        )
                    if resp.status_code in (429, 503):
                        backoff = (2**attempt) + random.uniform(0, 1)  # S311 safe: jitter only
                        await asyncio.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    content_length = resp.headers.get('content-length')
                    if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                        raise CendojNetworkError('Response too large')
                    if len(resp.content) > MAX_RESPONSE_BYTES:
                        raise CendojNetworkError('Response too large')
                    ct = resp.headers.get('content-type', '')
                    return resp.content, ct
                except (CendojNetworkError,):
                    raise
                except httpx.TimeoutException as exc:
                    if attempt == 2:
                        raise CendojNetworkError(f'Request timed out: {exc}') from exc
                    await asyncio.sleep(2**attempt)
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        raise CendojNetworkError(f'HTTP error: {exc}') from exc
                    await asyncio.sleep(2**attempt)
        raise CendojNetworkError('Max retries exceeded')

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Execute an HTTP request with retry logic.

        Args:
            method: HTTP method ('GET' or 'POST').
            url: Target URL.
            data: Optional form data for POST requests.

        Returns:
            Response body as string.

        Raises:
            CendojNetworkError: On unrecoverable failures.
        """
        async with self._semaphore:
            await asyncio.sleep(1.0 / RATE_LIMIT_RPS)
            for attempt in range(3):
                try:
                    if method == 'POST':
                        resp = await self._client.post(url, data=data)
                    else:
                        resp = await self._client.get(url)

                    if resp.status_code == 403:
                        raise CendojNetworkError(
                            'CENDOJ returned 403 — IP temporarily blocked by WAF. Wait 15–60 minutes before retrying.'
                        )
                    if resp.status_code == 500:
                        raise CendojNetworkError(
                            'CENDOJ returned 500 — the requested resource may not exist or the query is invalid.'
                        )
                    if resp.status_code in (429, 503):
                        backoff = (2**attempt) + random.uniform(0, 1)  # S311 safe: jitter only
                        await asyncio.sleep(backoff)
                        continue

                    resp.raise_for_status()

                    content_length = resp.headers.get('content-length')
                    if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                        raise CendojNetworkError('Response too large')
                    if len(resp.content) > MAX_RESPONSE_BYTES:
                        raise CendojNetworkError('Response too large')

                    return resp.text

                except (CendojNetworkError,):
                    raise
                except httpx.TimeoutException as exc:
                    if attempt == 2:
                        raise CendojNetworkError(f'Request timed out: {exc}') from exc
                    await asyncio.sleep(2**attempt)
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        raise CendojNetworkError(f'HTTP error: {exc}') from exc
                    await asyncio.sleep(2**attempt)
        raise CendojNetworkError('Max retries exceeded')

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
