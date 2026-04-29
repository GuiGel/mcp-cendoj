"""CENDOJ HTTP integration constants.

These values were captured via DevTools inspection and live HTTP probing of the
CENDOJ web portal (https://www.poderjudicial.es/search/indexAN.jsp) on 2026-04-29.

=== Live probe results ===

SEARCH MECHANISM:
- GET https://www.poderjudicial.es/search/indexAN.jsp → sets JSESSIONID cookie
- POST https://www.poderjudicial.es/search/search.action (with session cookie)
  Required fields: action='query', sort, recordsPerPage, databasematch, start, TEXT or ECLI
  Returns: HTML fragment with `<aside>` (filter sidebar) + `.resultswrapper` (result list)
  Do NOT set X-Requested-With header — server rejects that with "búsqueda no es válida"

ECLI LOOKUP:
- Same POST endpoint as search, but with ECLI=<ecli> field instead of TEXT
- Returns exactly 1 result if ECLI exists, 0 if not found
- Result item has: data-reference (internal ID), data-databasematch (tribunal),
  data-optimize (date YYYYMMDD), data-roj (ROJ), metadatos ECLI, title text

DOCUMENT RETRIEVAL:
- URL type: PDF (Option A is NOT applicable — CENDOJ serves all documents as PDFs)
- Fetch: GET https://www.poderjudicial.es/search/contenidos.action
  ?action=contentpdf&databasematch={db}&reference={internal_id}&optimize={date}&publicinterface=true
- Content-Type: application/pdf
- Session cookie required for this request too
- PDF text extracted via pdfplumber; raw_text wrapped in <court_document> boundary

GO/NO-GO GATE (2026-04-29):
- POST to search.action with TEXT='tutela judicial efectiva' returned 200
  with 148,595 total hits — endpoint is LIVE and functional
- ECLI lookup for 'ECLI:ES:TS:2026:3898A' returned exactly 1 result ✓
- Document fetch for reference=11699040 returned PDF (197,594 bytes) ✓
- PASSED: proceed with implementation
"""

# ---------------------------------------------------------------------------
# Endpoint URLs
# ---------------------------------------------------------------------------

CENDOJ_SEARCH_URL: str = 'https://www.poderjudicial.es/search/search.action'
"""POST endpoint for both full-text search and ECLI lookup.

Requires an active JSESSIONID session cookie obtained by first GETting
CENDOJ_SESSION_INIT_URL. Returns an HTML fragment (not a full page).
"""

CENDOJ_SESSION_INIT_URL: str = 'https://www.poderjudicial.es/search/indexAN.jsp'
"""GET this URL first to obtain the JSESSIONID session cookie required for all requests."""

CENDOJ_DOCUMENT_URL_TEMPLATE: str = (
    'https://www.poderjudicial.es/search/contenidos.action'
    '?action=contentpdf'
    '&databasematch={databasematch}'
    '&reference={reference}'
    '&optimize={optimize}'
    '&publicinterface=true'
)
"""URL template for fetching a ruling document (returns PDF).

Placeholders:
  {databasematch}  tribunal code from search result (e.g. 'TS', 'AN')
  {reference}      CENDOJ internal numeric ID from search result data-reference attribute
  {optimize}       date string in YYYYMMDD format from search result data-optimize attribute

All values come from the search result HTML — they are NOT derived from the ECLI.
Session cookie (JSESSIONID) is required.
"""

# ---------------------------------------------------------------------------
# Browser-mimicking headers
# ---------------------------------------------------------------------------

DEFAULT_HEADERS: dict[str, str] = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.poderjudicial.es/search/indexAN.jsp',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}
"""Minimal browser-mimicking request headers.

Must NOT include Cookie, Authorization, X-CSRF, X-Auth, or any session header.
Do NOT add X-Requested-With: XMLHttpRequest — the server rejects it with 403/error.
Session cookies (JSESSIONID) are managed automatically by the httpx client cookie jar.
"""

# ---------------------------------------------------------------------------
# Search form field values
# ---------------------------------------------------------------------------

SEARCH_ACTION_QUERY: str = 'query'
"""Value for the 'action' POST field that triggers a search."""

SEARCH_SORT_DEFAULT: str = 'IN_FECHARESOLUCION:decreasing'
"""Default sort order: by ruling date, newest first."""

SEARCH_DATABASE_ALL: str = 'TS'
"""Default tribunal/database to search. 'TS' = Tribunal Supremo."""

# ---------------------------------------------------------------------------
# Operational limits
# ---------------------------------------------------------------------------

MAX_RESULTS_DEFAULT: int = 10
MAX_RESULTS_CAP: int = 100

RATE_LIMIT_RPS: int = 1
"""Requests per second. Per-process — concurrent sessions are NOT serialised."""

CONNECT_TIMEOUT_S: float = 5.0
READ_TIMEOUT_S: float = 30.0

MAX_RESPONSE_BYTES: int = 10_485_760  # 10 MB hard cap on HTTP response bodies
MAX_HTML_BYTES: int = 2_000_000  # 2 MB hard cap before BeautifulSoup parsing
