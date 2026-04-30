"""Resource: fetch and cache a full CENDOJ ruling document by ECLI."""

import asyncio

from pydantic import ValidationError

from mcp_cendoj.cache import DiskCache
from mcp_cendoj.http import CendojClient
from mcp_cendoj.models import Ruling
from mcp_cendoj.parser import extract_sections
from mcp_cendoj.tools.lookup import lookup_by_ecli, validate_ecli

_DOCUMENT_FETCH_TIMEOUT_S = 20.0
"""Per-request HTTP read timeout for PDF document downloads, in seconds.

The document endpoint may return large PDF files (up to 1–2 MB). This is set
higher than READ_TIMEOUT_S to prevent premature timeouts on slow CENDOJ responses.
"""

_CACHE_TTL_SECONDS = 86_400  # 24 hours
"""Time-to-live for cached ruling documents, in seconds (24 hours).

After this period the cached entry expires and the document is re-fetched on
the next request. A 24-hour window balances freshness against the risk of
triggering CENDOJ WAF rate limits.
"""

_disk_cache: DiskCache | None = None


def _get_cache() -> DiskCache:
    """Return the module-level :class:`~mcp_cendoj.cache.DiskCache` singleton.

    The cache is created on first call and reused across all subsequent calls
    within the same process. This is a deliberate global to avoid the overhead
    of reopening the SQLite database on every request.
    """
    global _disk_cache
    if _disk_cache is None:
        _disk_cache = DiskCache()
    return _disk_cache


async def get_ruling_text(ecli: str, client: CendojClient | None = None, cache: DiskCache | None = None) -> Ruling:
    """Fetch the full text of a court ruling identified by *ecli*.

    Checks the local disk cache first. On a cache miss it:

    1. Looks up the ruling metadata via :func:`~mcp_cendoj.tools.lookup.lookup_by_ecli`.
    2. Downloads the PDF from the CENDOJ document endpoint.
    3. Extracts sections via :func:`~mcp_cendoj.parser.extract_sections`.
    4. Stores the enriched ruling in the cache with a 24-hour TTL.

    Args:
        ecli: The ECLI string identifying the ruling.
        client: Optional :class:`~mcp_cendoj.http.CendojClient` for HTTP requests.
        cache: Optional :class:`~mcp_cendoj.cache.DiskCache` for testing.

    Returns:
        A fully enriched :class:`~mcp_cendoj.models.Ruling` instance.

    Raises:
        ValueError: If the ECLI format is invalid.
        CendojNetworkError: On HTTP failures.
        TimeoutError: If the document fetch exceeds the timeout.
    """
    ecli = ecli.strip().upper()
    validate_ecli(ecli)

    effective_cache = cache if cache is not None else _get_cache()

    cached_json = await effective_cache.get(ecli)
    if cached_json:
        try:
            return Ruling.model_validate_json(cached_json)
        except ValidationError:
            pass  # Treat as cache miss

    own_client = client is None
    effective_client = client if client is not None else CendojClient()

    try:
        ruling = await asyncio.wait_for(
            lookup_by_ecli(ecli, client=effective_client),
            timeout=_DOCUMENT_FETCH_TIMEOUT_S,
        )

        content, content_type = await asyncio.wait_for(
            effective_client.get_with_content_type(ruling.source_url),
            timeout=_DOCUMENT_FETCH_TIMEOUT_S,
        )

        if 'pdf' in content_type.lower():
            sections = extract_sections(content, ecli=ecli)
            ruling = ruling.model_copy(update={'sections': sections})
    finally:
        if own_client:
            await effective_client.close()

    await effective_cache.set(ecli, ruling.model_dump_json(), ttl_seconds=_CACHE_TTL_SECONDS)
    return ruling
