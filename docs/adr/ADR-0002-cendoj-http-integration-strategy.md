# ADR-0002: CENDOJ HTTP Integration Strategy

**Date**: 2026-04-29
**Status**: Accepted

## Context

CENDOJ (https://www.poderjudicial.es/search/indexAN.jsp) provides no versioned public API. The search interface is a JSP/AJAX web application backed by undocumented internal endpoints. Options considered:

1. **Form-encoded POST scraping** — POST to the AJAX endpoint (`/search/AN/openAction.action`) discovered via browser DevTools, mimicking a browser session.
2. **Headless browser** — Use Playwright to drive the full browser session (handles cookies, JS, CSRF).
3. **Third-party legal API** — Use a commercial provider (Aranzadi, Tirant) that re-exposes CENDOJ data with a stable API.

## Decision

Use **option 1**: direct `httpx` async POST with browser-captured headers, rate-limited to 1 request/second.

Before writing any tool code, a throwaway script must assert that a live POST with captured headers returns at least one real ruling. The exact form-field names (`campo010`, `query`, `rows`, etc.) are locked into `constants.py` after this verification.

Headless browser (option 2) is out of scope for the MVP — adds ~30 MB dependency and operational complexity. It can be introduced later if the endpoint proves CSRF-protected.

### Required hardening

- `httpx.AsyncClient` reused across requests (connection pooling, cookie persistence within a session).
- `User-Agent` header set to a modern browser string.
- `Referer` header set to the CENDOJ search page URL.
- Exponential backoff on 429/503 (max 3 retries, jitter added).
- Hard rate limit of 1 req/s via `asyncio.Semaphore` + `asyncio.sleep`.
- `httpx.TimeoutException` wrapped in a domain-specific `CendojNetworkError`.
- Empty result set treated as a distinct error, not a silent success.

## Consequences

**Positive**:
- Zero additional heavyweight dependencies for the MVP.
- Async-native (`httpx` + `asyncio`) — compatible with FastMCP's async tool model.
- Easily mockable with `respx` for unit tests.

**Negative**:
- No official API contract — endpoint can change silently; integration tests against live HTML fixtures are mandatory.
- Subject to CGPJ rate limiting; concurrent multi-agent usage can trigger IP blocks.
- ToS do not explicitly prohibit programmatic access for personal use, but scraping at scale may violate them — document this in tool docstrings.
