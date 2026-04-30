"""CENDOJ HTTP integration constants.

All values were discovered via DevTools network inspection, live HTTP probing,
and Playwright form scraping of the CENDOJ web portal
(https://www.poderjudicial.es/search/indexAN.jsp) on 2026-04-29 and 2026-04-30.

=== How CENDOJ search works ===

SESSION:
  1. GET CENDOJ_SESSION_INIT_URL — the server sets an HttpOnly JSESSIONID cookie.
  2. Include that cookie in every subsequent POST (managed automatically by httpx).

SEARCH (jurisprudencia):
  POST CENDOJ_SEARCH_URL with Content-Type: application/x-www-form-urlencoded.
  Required base fields: CENDOJ_FORM_BASE (all hidden form fields, even empty ones).
  Add TEXT=<query> and recordsPerPage=<n> on top.

  CRITICAL — recordsPerPage restriction (verified 2026-04-30):
    Only the values 1, 10, 20, 50 are accepted. Any other value (e.g. 3, 5, 25)
    causes the server to return 200 with "La búsqueda no es válida!". This was
    discovered by exhaustive testing: values 1, 10, 20, 50 return results;
    all others return the error response (275 bytes).

  Response: HTML fragment — <aside> (filter sidebar) + .resultswrapper (result list).
  Each result: div.searchresult.doc → a[data-roj] for title/IDs,
               .metadatos ul li for ECLI and court, .summary for snippet.

  WAF: >~50 requests per minute from the same IP triggers a 403 block
       lasting 15–60 minutes.

LEGISLATION SEARCH (normas):
  POST CENDOJ_NORMAS_URL (different from CENDOJ_SEARCH_URL).
  Discovered via Playwright inspection of the doSearchNorma() JS function:
    url = contextPath + 'jurisprudencia.action'  →  /search/jurisprudencia.action
  Field name: TITULO (the HTML input has name="TITULO", id="searchNormaForm_TEXTNorma").
  Response: HTML fragment — input[totalhitsNorma] + ul > li.normaItem.level-1
    each li → input.normacheck[data-boe][data-title]  (data-boe = BOE reference ID).

ECLI LOOKUP:
  Same POST as search but send ECLI=<ecli> instead of TEXT.
  Returns exactly 1 result if found, 0 if not found.
  Result attributes: data-reference (internal ID), data-databasematch (tribunal
  code, e.g. 'TS'), data-optimize (YYYYMMDD), data-roj (ROJ string).

DOCUMENT RETRIEVAL:
  GET CENDOJ_DOCUMENT_URL_TEMPLATE with placeholders filled from search result.
  Returns application/pdf. Extract text via pdfplumber; wrap in <court_document>.
  Session cookie required.

GO/NO-GO GATE (2026-04-29):
  POST TEXT='tutela judicial efectiva' → 200, 148 595 hits (endpoint live).
  ECLI lookup 'ECLI:ES:TS:2026:3898A' → 1 result ✓
  Document fetch reference=11699040 → PDF 197 594 bytes ✓
"""

from typing import Literal, get_args

# ---------------------------------------------------------------------------
# Endpoint URLs
# ---------------------------------------------------------------------------

CENDOJ_NORMAS_URL: str = 'https://www.poderjudicial.es/search/jurisprudencia.action'
"""POST endpoint for the legislation (normas) index search.

This is a *different* endpoint from CENDOJ_SEARCH_URL. Discovered by inspecting
the ``doSearchNorma()`` JavaScript function in the CENDOJ portal, which builds
the URL as ``contextPath + 'jurisprudencia.action'``.

Expected form fields (see ``_NORMAS_BASE`` in tools/normas.py):
    action='getNormasList', databasematch='legislacion', TITULO=<query>, …

Response: HTML fragment with ``input[totalhitsNorma]`` + ``ul > li.normaItem.level-1``.
Each ``li`` contains ``input.normacheck[data-boe][data-title]`` where ``data-boe``
is the BOE reference ID (e.g. '2015/11430') needed as ``norma_id`` in search_rulings.
"""

CENDOJ_SEARCH_URL: str = 'https://www.poderjudicial.es/search/search.action'
"""POST endpoint for both full-text search and ECLI lookup.

Requires an active JSESSIONID session cookie obtained by first GETting
CENDOJ_SESSION_INIT_URL. Returns an HTML fragment (not a full HTML page).

Critical constraint — recordsPerPage:
    Only the values 1, 10, 20, 50 are valid. Any other value causes a 200
    response with the body ``"La búsqueda no es válida!"`` (275 bytes).
    See ``_valid_page_sizes`` in :func:`~mcp_cendoj.tools.search.search_rulings`.
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
"""Minimal browser-mimicking request headers sent with every CENDOJ request.

Do NOT include Cookie, Authorization, X-CSRF, X-Auth, or any other session header;
httpx manages the JSESSIONID cookie automatically via its cookie jar.

Note on X-Requested-With: The real browser's jQuery AJAX sends
``X-Requested-With: XMLHttpRequest``, but it has no effect on server-side
validation — including or omitting it makes no difference (verified 2026-04-30).
"""

# ---------------------------------------------------------------------------
# Search form field values
# ---------------------------------------------------------------------------

SEARCH_ACTION_QUERY: str = 'query'
"""Value for the 'action' POST field that triggers a search."""

SEARCH_SORT_DEFAULT: str = 'IN_FECHARESOLUCION:decreasing'
"""Default sort order: by ruling date, newest first."""

SEARCH_DATABASE_ALL: str = 'AN'
"""Database/tab identifier for jurisprudencia queries.

'AN' is the value the CENDOJ search form sends by default and is required for
the server to process the request. Results still include all tribunal levels
(TS, AN, TSJ, AP, …); it does NOT restrict to Audiencia Nacional.
"""

CENDOJ_FORM_BASE: dict[str, str] = {
    'action': SEARCH_ACTION_QUERY,
    'sort': SEARCH_SORT_DEFAULT,
    'databasematch': SEARCH_DATABASE_ALL,
    'start': '1',
    # All filter fields follow; they are sent as empty strings when unused.
    # These mirror every hidden <input> in the frmBusquedajurisprudencia form
    # (scraped via Playwright on 2026-04-30). The CENDOJ server appears tolerant
    # of missing filter keys as long as recordsPerPage is a valid value.
    'lastsentences': '',
    'ANYO': '',
    'maxresults': '',
    'page': '',
    'ID_NORMA': '',  # BOE reference ID from search_normas (e.g. '2015/11430')
    'ARTICULO': '',  # Article number(s) within the above norm
    'org': '',
    'ccaa': '',
    'land': '',
    'TIPOINTERES_INSTITUCIONES': '',
    'INSTITUCION': '',
    'landing': '',
    'landingtype': '',
    'repetitivas': '',
    'FECHAENTRADA': '',
    'JURISDICCION': '',  # see CendojJurisdiccion
    'TIPORESOLUCION': '',
    'SUBTIPORESOLUCION': '',  # see CendojTipoResolucion
    'SECCIONAUTO': '',  # see CendojSeccionAuto
    'TIPOORGANOPUB': '',  # see TRIBUNAL_CODES
    'SECCION': '',
    'VALUESCOMUNIDAD': '',  # see COMUNIDAD_WIRE
    'ROJ': '',
    'ECLI': '',
    'FECHARESOLUCIONDESDE': '',  # DD/MM/YYYY
    'NUMERORESOLUCION': '',
    'FECHARESOLUCIONHASTA': '',  # DD/MM/YYYY
    'NUMERORECURSO': '',
    'PONENTE': '',
    'IDIOMA': '',  # see CendojIdioma
    'NORMA': '',  # display-only label; server uses ID_NORMA for filtering
    'TIPOINTERES_JURIDICO': '',
    'TIPOINTERES_ACTUAL': '',
    'TIPOINTERES_IGUALDAD': '',
    'TIPOINTERES_DISCAPACIDAD': '',
    'TIPOINTERES_LECTURAFACIL': '',
    'HISTORICOPUBLICO': '',
}
"""Base form payload for all jurisprudencia POST requests to CENDOJ_SEARCH_URL.

Contains every hidden field from the ``frmBusquedajurisprudencia`` form with
their default values. Callers merge query-specific fields on top::

    data = {**CENDOJ_FORM_BASE, **extra_filters, 'recordsPerPage': '10', 'TEXT': query}

RecordsPerPage MUST be one of {1, 10, 20, 50} — any other value causes the
server to return the error page "La búsqueda no es válida!".
"""

# ---------------------------------------------------------------------------
# Enum types for CENDOJ filter fields
# Source: Playwright form scrape of indexAN.jsp on 2026-04-30
# ---------------------------------------------------------------------------

CendojJurisdiccion = Literal['CIVIL', 'PENAL', 'CONTENCIOSO', 'SOCIAL', 'MILITAR', 'ESPECIAL']
"""Legal branch filter (JURISDICCION field).

- CIVIL       — Civil law
- PENAL       — Criminal law
- CONTENCIOSO — Administrative/contentious law
- SOCIAL      — Labour & social security law
- MILITAR     — Military law
- ESPECIAL    — Special jurisdiction
"""

CendojTipoResolucion = Literal[
    'AUTO',
    'AUTO ACLARATORIO',
    'AUTO RECURSO',
    'AUTO ADMISION',
    'AUTO INADMISION',
    'AUTO OTROS',
    'SENTENCIA',
    'SENTENCIA CASACION',
    'SENTENCIA OTRAS',
    'ACUERDO',
]
"""Resolution type filter (SUBTIPORESOLUCION field).

'SENTENCIA' covers all judgments; 'SENTENCIA CASACION' is cassation-only.
'AUTO *' covers procedural orders. 'ACUERDO' covers agreements/accords.
"""

CendojIdioma = Literal['1', '2', '3', '4']
"""Document language filter (IDIOMA field).

- '1' — Español (Spanish)
- '2' — Català (Catalan)
- '3' — Galego (Galician)
- '4' — Euskera (Basque)

Omit (empty string) to return documents in all languages.
"""

# Tribunal code → human-readable label mapping (TIPOORGANOPUB field).
# Group codes (pipe-separated) select the entire court; individual codes select a sala.
# Source: Playwright form scrape of indexAN.jsp on 2026-04-30.
TRIBUNAL_CODES: dict[str, str] = {
    '11|12|13|14|15|16': 'Tribunal Supremo (todas las salas)',
    '11': 'Tribunal Supremo. Sala de lo Civil',
    '12': 'Tribunal Supremo. Sala de lo Penal',
    '13': 'Tribunal Supremo. Sala de lo Contencioso',
    '14': 'Tribunal Supremo. Sala de lo Social',
    '15': 'Tribunal Supremo. Sala de lo Militar',
    '16': 'Tribunal Supremo. Sala de lo Especial',
    '22|2264|23|24|25|26|27|28|29': 'Audiencia Nacional (todas las salas)',
    '22': 'Audiencia Nacional. Sala de lo Penal',
    '2264': 'Sala de Apelación de la Audiencia Nacional',
    '23': 'Audiencia Nacional. Sala de lo Contencioso',
    '24': 'Audiencia Nacional. Sala de lo Social',
    '25': 'Audiencia Nacional. Juzgado Central de Vigilancia Penitenciaria',
    '26': 'Audiencia Nacional. Juzgado Central de Menores',
    '27': 'Audiencia Nacional. Juzgados Centrales de Instrucción',
    '28': 'Audiencia Nacional. Juzgados Centrales de lo Penal',
    '29': 'Audiencia Nacional. Juzgados Centrales de lo Contencioso',
    '31|31201202|33|34': 'Tribunal Superior de Justicia (todas las salas)',
    '31': 'Tribunal Superior de Justicia. Sala de lo Civil y Penal',
    '31201202': 'Sección de Apelación Penal. TSJ Sala de lo Civil y Penal',
    '33': 'Tribunal Superior de Justicia. Sala de lo Contencioso',
    '34': 'Tribunal Superior de Justicia. Sala de lo Social',
    '36': 'Audiencia Territorial',
    '37': 'Audiencia Provincial',
    '38': 'Audiencia Provincial. Tribunal Jurado',
    '41': 'Juzgado de 1ª Inst. e Instrucción',
    '42': 'Juzgado de Primera Instancia',
    '43': 'Juzgado de Instrucción',
    '44': 'Juzgado de lo Social',
    '45': 'Juzgado de lo Contencioso Administrativo',
    '47': 'Juzgado de lo Mercantil',
    '48': 'Juzgado de Violencia sobre la Mujer',
    '51': 'Juzgado de lo Penal',
    '52': 'Juzgado de Vigilancia Penitenciaria',
    '53': 'Juzgado de Menores',
    '75': 'Consejo Supremo de Justicia Militar',
    '83': 'Tribunal Militar Territorial',
    '85': 'Tribunal Militar Central',
    '1001': 'Tribunal de Marca de la UE',
    '1002': 'Juzgados de Marca de la UE',
}
"""Mapping from TIPOORGANOPUB code to human-readable court name.

Pass the key as ``tipo_organo`` in :func:`~mcp_cendoj.tools.search.search_rulings`.
Group codes (containing ``|``) select all salas of a court. Individual numeric
codes select a specific sala.
"""

CendojSeccionAuto = Literal['2', '3', '4', '1']
"""TS Auto section filter (SECCIONAUTO field).

Only meaningful when searching TS Autos (procedural orders).
- '2' — Segunda sección
- '3' — Tercera sección
- '4' — Cuarta sección
- '1' — Quinta sección

Omit (None) to search all sections.
"""

CendojComunidad = Literal[
    'ANDALUCÍA',
    'ARAGÓN',
    'ASTURIAS',
    'BALEARES',
    'CANARIAS',
    'CANTABRIA',
    'CASTILLA_LA_MANCHA',
    'CASTILLA_Y_LEÓN',
    'CATALUÑA',
    'CEUTA',
    'COMUNIDAD_VALENCIANA',
    'EXTREMADURA',
    'GALICIA',
    'LA_RIOJA',
    'MADRID',
    'MELILLA',
    'MURCIA',
    'NAVARRA',
    'PAÍS_VASCO',
]
"""Autonomous community for the Localización filter (VALUESCOMUNIDAD field).

When set, the server receives the value as ``"<COMUNIDAD>(C) | "``
(e.g. ``"MADRID(C) | "``). This is the format the CENDOJ JS builds from
the community checkbox selection — validated via Playwright on 2026-04-30.
"""

# Maps CendojComunidad label → VALUESCOMUNIDAD wire format
COMUNIDAD_WIRE: dict[str, str] = {c: f'{c}(C) | ' for c in get_args(CendojComunidad)}
"""Mapping from CendojComunidad label to the VALUESCOMUNIDAD POST field value.

The server expects the format ``"CCAA(C) | "`` (trailing pipe and space).
This mirrors what the CENDOJ JavaScript builds from each community checkbox:
``$("#chkCOM_" + ccaa).val()`` appended to the VALUESCOMUNIDAD field.
Verified via Playwright on 2026-04-30.
"""

# TIPOINTERES_* wire values (set by clicking the interest icons — Playwright verified 2026-04-30)
TIPOINTERES_VALUES: dict[str, str] = {
    'TIPOINTERES_JURIDICO': 'Interés Jurídico',
    'TIPOINTERES_ACTUAL': 'Actualidad',
    'TIPOINTERES_IGUALDAD': 'Igualdad',
    'TIPOINTERES_DISCAPACIDAD': 'Discapacidad',
    'TIPOINTERES_LECTURAFACIL': 'Lectura fácil',
    'HISTORICOPUBLICO': 'true',
}
"""Wire values for the TIPOINTERES_* and HISTORICOPUBLICO hidden fields.

Each key is the form field name; each value is what the server receives when
the corresponding icon is activated in the UI.
"""

# ---------------------------------------------------------------------------
# Operational limits
# ---------------------------------------------------------------------------

MAX_RESULTS_DEFAULT: int = 10
"""Default number of results returned when max_results is not specified."""

MAX_RESULTS_CAP: int = 50
"""Hard ceiling for results per request, matching the largest valid recordsPerPage (50).

CENDOJ only accepts recordsPerPage ∈ {1, 10, 20, 50}. Requesting any other value
returns a 200 response containing "La búsqueda no es válida!" (verified 2026-04-30
by exhaustive testing of values 1–100).
"""

RATE_LIMIT_RPS: int = 1
"""Maximum requests per second issued by a single CendojClient instance.

This is enforced per-process via an asyncio.Semaphore. Multiple concurrent
processes (e.g. separate Claude Desktop sessions) each have their own limiter
and are NOT serialised across process boundaries.
"""

CONNECT_TIMEOUT_S: float = 5.0
"""TCP connection timeout in seconds for all CENDOJ requests."""

READ_TIMEOUT_S: float = 30.0
"""Read (response body) timeout in seconds. CENDOJ PDF downloads can be slow."""

MAX_RESPONSE_BYTES: int = 10_485_760  # 10 MB
"""Hard upper bound on the size of any HTTP response body (10 MiB).

Responses exceeding this limit are rejected with CendojNetworkError before
the body is fully read, preventing memory exhaustion on unexpectedly large
responses.
"""

MAX_HTML_BYTES: int = 2_000_000  # 2 MB
"""Maximum HTML response size accepted before passing to BeautifulSoup (2 MiB).

Prevents the lxml parser from consuming excessive memory on malformed or
unexpectedly large HTML fragments.
"""
