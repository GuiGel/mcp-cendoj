"""Tool: search CENDOJ for Spanish court rulings."""

from datetime import UTC, datetime
from typing import Annotated

from bs4 import BeautifulSoup
from pydantic import ConfigDict, Field, validate_call

from mcp_cendoj.constants import (
    CENDOJ_DOCUMENT_URL_TEMPLATE,
    CENDOJ_FORM_BASE,
    CENDOJ_SEARCH_URL,
    COMUNIDAD_WIRE,
    MAX_RESULTS_CAP,
    TIPOINTERES_VALUES,
    CendojComunidad,
    CendojIdioma,
    CendojJurisdiccion,
    CendojSeccionAuto,
    CendojTipoResolucion,
)
from mcp_cendoj.http import CendojClient
from mcp_cendoj.models import SearchResult


def _parse_search_results(html: str) -> list[SearchResult]:
    """Parse search results from a CENDOJ HTML response fragment.

    Expects the HTML returned by CENDOJ_SEARCH_URL for a ``action=query`` POST.
    The fragment structure is::

        <aside>
          <div class="filtersidebar"> ... </div>   # filter sidebar (ignored)
        </aside>
        <div class="resultswrapper">
          <div class="searchresult doc" data-fechares="YYYYMMDD" ...>
            <a data-roj="..." data-reference="..." data-databasematch="..." data-optimize="YYYYMMDD">
              <title text>
            </a>
            <div class="metadatos">
              <ul>
                <li><b>ECLI:ES:...</b></li>   # first li → ECLI
                <li>Court name</li>            # second li → court
              </ul>
            </div>
            <div class="summary">snippet text</div>
          </div>
          ...
        </div>

    Args:
        html: HTML fragment returned by the CENDOJ search endpoint.

    Returns:
        List of :class:`~mcp_cendoj.models.SearchResult` objects in document
        order (newest-first by default sort).
    """
    soup = BeautifulSoup(html, 'lxml')
    results: list[SearchResult] = []
    for result_div in soup.select('div.searchresult.doc'):
        title_link = result_div.select_one('a[data-roj]')
        if not title_link:
            continue

        reference = str(title_link.get('data-reference', '') or '')
        databasematch = str(title_link.get('data-databasematch', '') or '')
        optimize = str(title_link.get('data-optimize', '') or '')
        title = title_link.get_text(strip=True)

        ecli_elem = result_div.select_one('.metadatos ul li b')
        ecli_text: str | None = ecli_elem.get_text(strip=True) if ecli_elem else None

        court_li = result_div.select('.metadatos ul li')
        court = court_li[1].get_text(strip=True) if len(court_li) > 1 else ''

        date_raw = str(result_div.get('data-fechares', '') or '')
        date = f'{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}' if len(date_raw) == 8 else date_raw

        snippet_elem = result_div.select_one('.summary')
        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

        source_url = CENDOJ_DOCUMENT_URL_TEMPLATE.format(
            databasematch=databasematch,
            reference=reference,
            optimize=optimize,
        )

        results.append(
            SearchResult(
                ecli=ecli_text,
                title=title,
                court=court,
                date=date,
                snippet=snippet,
                url=source_url,
                fetched_at=datetime.now(tz=UTC),
                freshness='unknown',
            )
        )
    return results


def _build_interest_fields(
    *,
    interes_ts: bool,
    actualidad: bool,
    igualdad_genero: bool,
    discapacidad: bool,
    lectura_facil: bool,
    historico_ts: bool,
) -> dict[str, str]:
    """Build TIPOINTERES_* and HISTORICOPUBLICO POST fields from boolean flags.

    Each flag corresponds to a clickable icon in the CENDOJ search form that
    sends a specific string value when active. Values come from TIPOINTERES_VALUES.

    Args:
        interes_ts: Set TIPOINTERES_JURIDICO to flag Tribunal Supremo legal-interest rulings.
        actualidad: Set TIPOINTERES_ACTUAL to flag recently-highlighted rulings.
        igualdad_genero: Set TIPOINTERES_IGUALDAD for gender-equality rulings.
        discapacidad: Set TIPOINTERES_DISCAPACIDAD for disability-related rulings.
        lectura_facil: Set TIPOINTERES_LECTURAFACIL for plain-language rulings.
        historico_ts: Set HISTORICOPUBLICO='true' to include pre-1979 TS archive.

    Returns:
        Dict of POST field name → wire value for each active flag.
        Empty dict when all flags are False.
    """
    extra: dict[str, str] = {}
    if interes_ts:
        extra['TIPOINTERES_JURIDICO'] = TIPOINTERES_VALUES['TIPOINTERES_JURIDICO']
    if actualidad:
        extra['TIPOINTERES_ACTUAL'] = TIPOINTERES_VALUES['TIPOINTERES_ACTUAL']
    if igualdad_genero:
        extra['TIPOINTERES_IGUALDAD'] = TIPOINTERES_VALUES['TIPOINTERES_IGUALDAD']
    if discapacidad:
        extra['TIPOINTERES_DISCAPACIDAD'] = TIPOINTERES_VALUES['TIPOINTERES_DISCAPACIDAD']
    if lectura_facil:
        extra['TIPOINTERES_LECTURAFACIL'] = TIPOINTERES_VALUES['TIPOINTERES_LECTURAFACIL']
    if historico_ts:
        extra['HISTORICOPUBLICO'] = TIPOINTERES_VALUES['HISTORICOPUBLICO']
    return extra


def _build_norma_fields(norma_id: str | None, articulo: str | None) -> dict[str, str]:
    """Build the ID_NORMA and ARTICULO POST fields for legislation filtering.

    The ``ID_NORMA`` field is the BOE reference ID returned by
    :func:`~mcp_cendoj.tools.normas.search_normas` (e.g. ``'2015/11430'``).
    It is NOT the ``NORMA`` display-label field (which is ignored server-side).

    Args:
        norma_id: BOE reference ID of the legislation to filter by, or None.
        articulo: Article number(s) within the norm (e.g. ``'14'`` or ``'14,15'``).
            Only meaningful when *norma_id* is also set.

    Returns:
        Dict with ``'ID_NORMA'`` and/or ``'ARTICULO'`` keys, or empty dict when
        both arguments are None.
    """
    extra: dict[str, str] = {}
    if norma_id is not None:
        extra['ID_NORMA'] = norma_id
    if articulo is not None:
        extra['ARTICULO'] = articulo
    return extra


def _build_extra_fields(
    *,
    jurisdiccion: CendojJurisdiccion | None,
    tipo_resolucion: CendojTipoResolucion | None,
    tipo_organo: str | None,
    idioma: CendojIdioma | None,
    fecha_desde: str | None,
    fecha_hasta: str | None,
    ponente: str | None,
    roj: str | None,
    numero_resolucion: str | None,
    numero_recurso: str | None,
    norma_id: str | None,
    articulo: str | None,
    comunidad: CendojComunidad | None,
    seccion_auto: CendojSeccionAuto | None,
    interes_ts: bool,
    actualidad: bool,
    igualdad_genero: bool,
    discapacidad: bool,
    lectura_facil: bool,
    historico_ts: bool,
) -> dict[str, str]:
    """Assemble the optional POST filter fields dict from caller parameters.

    Maps each high-level parameter to its wire POST field name and value.
    Only non-None / True parameters produce entries in the returned dict;
    omitted entries cause the CENDOJ_FORM_BASE default (empty string) to be used.

    Parameter → POST field mapping:
        jurisdiccion → JURISDICCION
        tipo_resolucion → SUBTIPORESOLUCION
        tipo_organo → TIPOORGANOPUB
        idioma → IDIOMA
        fecha_desde → FECHARESOLUCIONDESDE
        fecha_hasta → FECHARESOLUCIONHASTA
        ponente → PONENTE
        roj → ROJ
        numero_resolucion → NUMERORESOLUCION
        numero_recurso → NUMERORECURSO
        norma_id → ID_NORMA  (via _build_norma_fields)
        articulo → ARTICULO   (via _build_norma_fields)
        comunidad → VALUESCOMUNIDAD  (via COMUNIDAD_WIRE lookup)
        seccion_auto → SECCIONAUTO
        interes_ts / actualidad / … → TIPOINTERES_*  (via _build_interest_fields)

    Args:
        jurisdiccion: Legal branch filter value.
        tipo_resolucion: Resolution type filter value.
        tipo_organo: TIPOORGANOPUB code (see TRIBUNAL_CODES).
        idioma: Language code (see CendojIdioma).
        fecha_desde: Earliest date in DD/MM/YYYY format.
        fecha_hasta: Latest date in DD/MM/YYYY format.
        ponente: Magistrate surname.
        roj: ROJ identifier.
        numero_resolucion: Resolution number.
        numero_recurso: Appeal number.
        norma_id: BOE reference ID (from search_normas).
        articulo: Article number(s) within the norm.
        comunidad: Autonomous community value.
        seccion_auto: TS Auto section code.
        interes_ts: Activate Interés Jurídico flag.
        actualidad: Activate Actualidad flag.
        igualdad_genero: Activate Igualdad flag.
        discapacidad: Activate Discapacidad flag.
        lectura_facil: Activate Lectura Fácil flag.
        historico_ts: Activate Histórico TS flag.

    Returns:
        Dict of POST field name → wire value. Merge over CENDOJ_FORM_BASE.
    """
    extra: dict[str, str] = {}
    if jurisdiccion is not None:
        extra['JURISDICCION'] = jurisdiccion
    if tipo_resolucion is not None:
        extra['SUBTIPORESOLUCION'] = tipo_resolucion
    if tipo_organo is not None:
        extra['TIPOORGANOPUB'] = tipo_organo
    if idioma is not None:
        extra['IDIOMA'] = idioma
    if fecha_desde is not None:
        extra['FECHARESOLUCIONDESDE'] = fecha_desde
    if fecha_hasta is not None:
        extra['FECHARESOLUCIONHASTA'] = fecha_hasta
    if ponente is not None:
        extra['PONENTE'] = ponente
    if roj is not None:
        extra['ROJ'] = roj
    if numero_resolucion is not None:
        extra['NUMERORESOLUCION'] = numero_resolucion
    if numero_recurso is not None:
        extra['NUMERORECURSO'] = numero_recurso
    extra |= _build_norma_fields(norma_id, articulo)
    if comunidad is not None:
        extra['VALUESCOMUNIDAD'] = COMUNIDAD_WIRE[comunidad]
    if seccion_auto is not None:
        extra['SECCIONAUTO'] = seccion_auto
    extra |= _build_interest_fields(
        interes_ts=interes_ts,
        actualidad=actualidad,
        igualdad_genero=igualdad_genero,
        discapacidad=discapacidad,
        lectura_facil=lectura_facil,
        historico_ts=historico_ts,
    )
    return extra


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
async def search_rulings(
    query: str,
    max_results: Annotated[int, Field(ge=1)] = 10,
    jurisdiccion: CendojJurisdiccion | None = None,
    tipo_resolucion: CendojTipoResolucion | None = None,
    tipo_organo: str | None = None,
    idioma: CendojIdioma | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    ponente: str | None = None,
    roj: str | None = None,
    numero_resolucion: str | None = None,
    numero_recurso: str | None = None,
    norma_id: str | None = None,
    articulo: str | None = None,
    comunidad: CendojComunidad | None = None,
    seccion_auto: CendojSeccionAuto | None = None,
    seccion: str | None = None,
    solo_pleno: bool = False,
    interes_ts: bool = False,
    actualidad: bool = False,
    igualdad_genero: bool = False,
    discapacidad: bool = False,
    lectura_facil: bool = False,
    historico_ts: bool = False,
    client: CendojClient | None = None,
) -> list[SearchResult]:
    """Search CENDOJ for Spanish court rulings matching a free-text query.

    Rate limiting: 1 request/second per process. Concurrent Claude Desktop
    sessions (separate processes) are not serialised — each has its own
    rate limiter. Avoid querying this tool at high frequency.

    Terms of Service: Use only for legal research on publicly available rulings.
    This tool does not circumvent authentication or access controls.

    Freshness: Results include a provenance envelope with fetched_at timestamp
    and freshness='unknown'. CENDOJ does not expose document modification dates.

    Text operators: embed Y (AND), O (OR), NO (NOT), PROX20 (proximity/near)
    directly in the query string, e.g. ``'despido Y nulidad'``.

    Args:
        query: Free-text search query. Supports Boolean operators: Y (AND),
            O (OR), NO (NOT), PROX20 (proximity). Example: 'despido Y nulidad'.
        max_results: Maximum number of results to return. Rounded up internally
            to the nearest valid CENDOJ page size (1, 10, 20, or 50) and then
            trimmed to the requested count. Values above 50 are clamped to 50.
        jurisdiccion: Legal branch. One of: 'CIVIL', 'PENAL', 'CONTENCIOSO',
            'SOCIAL', 'MILITAR', 'ESPECIAL'. Omit for all.
        tipo_resolucion: Resolution type. One of: 'SENTENCIA
            CASACION', 'SENTENCIA OTRAS', 'AUTO ACLARATORIO',
            'AUTO RECURSO', 'AUTO ADMISION', 'AUTO INADMISION', 'AUTO OTROS',
            'ACUERDO'. Omit for all types. Note: parent-category values
            'SENTENCIA' and 'AUTO' are not supported (CENDOJ returns no results
            for them); use the specific subtypes above.
        tipo_organo: Court/tribunal code from TRIBUNAL_CODES. Examples:
            '14' = TS Social, '34' = TSJ Social, '44' = Juzgado Social,
            '11|12|13|14|15|16' = entire Tribunal Supremo. Omit for all courts.
        idioma: Document language. '1'=Español, '2'=Català, '3'=Galego,
            '4'=Euskera. Omit for all languages.
        fecha_desde: Earliest ruling date in DD/MM/YYYY format (inclusive).
        fecha_hasta: Latest ruling date in DD/MM/YYYY format (inclusive).
        ponente: Judge (magistrate) surname filter. Partial match supported.
        roj: ROJ identifier filter (e.g. 'STS 1234/2024').
        numero_resolucion: Resolution number filter.
        numero_recurso: Appeal/recurso number filter.
        norma_id: Legislation filter — returns only rulings that cite this law.
            Use the BOE reference ID returned by the search_normas tool
            (e.g. '2015/11430' for the Estatuto de los Trabajadores). This
            populates the ID_NORMA form field used for server-side filtering.
        articulo: Article number(s) within the norm selected by norma_id.
            Comma-separated for multiple articles (e.g. '14' or '14,15').
            Only meaningful when norma_id is also set.
        comunidad: Autonomous community filter. One of the 19 CCAA values
            (e.g. 'MADRID', 'CATALUÑA', 'PAÍS_VASCO'). Omit for all Spain.
        seccion_auto: TS Auto section. '2'=Segunda, '3'=Tercera, '4'=Cuarta,
            '1'=Quinta. Only meaningful with tipo_organo TS + AUTO resolutions.
        seccion: Section number filter (free text). Filters to a specific
            numbered section of the court (e.g. '1', '23').
        solo_pleno: If True, restrict to plenary session decisions only
            (Sólo pleno). Sends SECCIONSOLOPLENO=true.
        interes_ts: If True, restrict to rulings flagged as Interés Jurídico
            by the Tribunal Supremo.
        actualidad: If True, restrict to rulings flagged as Actualidad
            (recently highlighted by CENDOJ editors).
        igualdad_genero: If True, restrict to rulings flagged for gender
            equality relevance.
        discapacidad: If True, restrict to rulings flagged for disability
            relevance.
        lectura_facil: If True, restrict to rulings available in plain-language
            (lectura fácil) format.
        historico_ts: If True, include rulings published before 1979
            (historic TS archive). Default False searches post-1978 only.
        client: Optional CendojClient instance; creates a fresh one if not given.

    Returns:
        List of SearchResult objects, ordered by ruling date descending.

    Raises:
        CendojNetworkError: On HTTP failures or empty result sets.
    """
    max_results = min(max_results, MAX_RESULTS_CAP)
    # CENDOJ only accepts recordsPerPage ∈ {1, 10, 20, 50}.
    # Any other value returns a 200 response with "La búsqueda no es válida!"
    # (275-byte error page). Round up to the smallest valid size that covers
    # max_results, then slice the result list down to the requested count.
    _valid_page_sizes = (1, 10, 20, 50)
    records_per_page = next((v for v in _valid_page_sizes if v >= max_results), 50)
    extra = _build_extra_fields(
        jurisdiccion=jurisdiccion,
        tipo_resolucion=tipo_resolucion,
        tipo_organo=tipo_organo,
        idioma=idioma,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        ponente=ponente,
        roj=roj,
        numero_resolucion=numero_resolucion,
        numero_recurso=numero_recurso,
        norma_id=norma_id,
        articulo=articulo,
        comunidad=comunidad,
        seccion_auto=seccion_auto,
        interes_ts=interes_ts,
        actualidad=actualidad,
        igualdad_genero=igualdad_genero,
        discapacidad=discapacidad,
        lectura_facil=lectura_facil,
        historico_ts=historico_ts,
    )
    if seccion is not None:
        extra['SECCION'] = seccion
    if solo_pleno:
        extra['SECCIONSOLOPLENO'] = 'true'

    own_client = client is None
    if own_client:
        client = CendojClient()
    try:
        html = await client.post(
            CENDOJ_SEARCH_URL,
            data={
                **CENDOJ_FORM_BASE,
                **extra,
                'recordsPerPage': str(records_per_page),
                'TEXT': query,
            },
        )
    finally:
        if own_client:
            await client.close()

    results = _parse_search_results(html)
    return results[:max_results]
