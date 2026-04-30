"""MCP server for the CENDOJ Spanish judicial database."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_cendoj.cache import DiskCache
from mcp_cendoj.constants import (
    CendojComunidad,
    CendojIdioma,
    CendojJurisdiccion,
    CendojSeccionAuto,
    CendojTipoResolucion,
)
from mcp_cendoj.http import CendojClient
from mcp_cendoj.models import NormaResult, Ruling, SearchResult, SupersededResult
from mcp_cendoj.tools.document import get_ruling_text as _document_impl
from mcp_cendoj.tools.lookup import lookup_by_ecli as _lookup_impl
from mcp_cendoj.tools.normas import search_normas as _normas_impl
from mcp_cendoj.tools.search import search_rulings as _search_impl
from mcp_cendoj.tools.superseded import check_if_superseded as _superseded_impl

app = FastMCP('mcp-cendoj')

_client: CendojClient | None = None  # set in tests via monkeypatch; None = prod default
_disk_cache: DiskCache | None = None  # test-injectable cache for resource; None = prod default


@app.tool()
async def lookup_by_ecli(ecli: str) -> Ruling:
    """Look up a Spanish court ruling by its ECLI identifier.

    Args:
        ecli: The ECLI string (e.g. 'ECLI:ES:TS:2020:1234').

    Returns:
        A Ruling with metadata and snippet text.
    """
    return await _lookup_impl(ecli, client=_client)


@app.tool()
async def search_rulings(
    query: str,
    max_results: Annotated[int, Field(ge=1, le=100)] = 10,
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
) -> list[SearchResult]:
    """Search CENDOJ for Spanish court rulings matching a free-text query.

    Text operators: Y (AND), O (OR), NO (NOT), PROX20 (proximity).
    Example: 'despido Y nulidad'.

    Args:
        query: Free-text search query (Boolean operators Y/O/NO/PROX20 supported).
        max_results: Maximum number of results (1–100).
        jurisdiccion: Legal branch: 'CIVIL', 'PENAL', 'CONTENCIOSO', 'SOCIAL',
            'MILITAR', 'ESPECIAL'. Omit for all.
        tipo_resolucion: Resolution type: 'SENTENCIA', 'SENTENCIA CASACION',
            'SENTENCIA OTRAS', 'AUTO', 'AUTO ACLARATORIO', 'AUTO RECURSO',
            'AUTO ADMISION', 'AUTO INADMISION', 'AUTO OTROS', 'ACUERDO'.
        tipo_organo: Court code (e.g. '14'=TS Social, '34'=TSJ Social, '44'=Juzgado
            Social, '11|12|13|14|15|16'=entire TS). Omit for all courts.
        idioma: Document language: '1'=Español, '2'=Català, '3'=Galego, '4'=Euskera.
        fecha_desde: Earliest ruling date DD/MM/YYYY (inclusive).
        fecha_hasta: Latest ruling date DD/MM/YYYY (inclusive).
        ponente: Judge surname filter. Partial match supported.
        roj: ROJ identifier filter (e.g. 'STS 1234/2024').
        numero_resolucion: Resolution number filter.
        numero_recurso: Appeal number filter.
        norma_id: BOE reference ID from search_normas (e.g. '2015/11430'). Filters
            to rulings citing that law. Use search_normas tool to find the ID.
        articulo: Article number(s) within norma_id (e.g. '14' or '14,15').
        comunidad: Autonomous community: 'MADRID', 'CATALUÑA', 'PAÍS_VASCO', etc.
        seccion_auto: TS Auto section: '2'=Segunda, '3'=Tercera, '4'=Cuarta,
            '1'=Quinta.
        seccion: Section number of the court (e.g. '1', '23').
        solo_pleno: If True, restrict to plenary session decisions only.
        interes_ts: If True, restrict to rulings flagged as Interés Jurídico by TS.
        actualidad: If True, restrict to editorially highlighted rulings.
        igualdad_genero: If True, restrict to gender equality flagged rulings.
        discapacidad: If True, restrict to disability-relevant rulings.
        lectura_facil: If True, restrict to plain-language format rulings.
        historico_ts: If True, include pre-1979 historic TS archive.

    Returns:
        List of SearchResult objects ordered by ruling date descending.
    """
    return await _search_impl(
        query,
        max_results,
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
        seccion=seccion,
        solo_pleno=solo_pleno,
        interes_ts=interes_ts,
        actualidad=actualidad,
        igualdad_genero=igualdad_genero,
        discapacidad=discapacidad,
        lectura_facil=lectura_facil,
        historico_ts=historico_ts,
        client=_client,
    )


@app.tool()
async def search_normas(titulo: str) -> list[NormaResult]:
    """Search the CENDOJ legislation index to look up a norm's BOE reference ID.

    Use this tool to discover the norma_id value (e.g. '2015/11430') for
    use with the norma_id parameter of search_rulings.

    Args:
        titulo: Free-text search for the legislation title.

    Returns:
        List of NormaResult objects, each with norma_id and title.
    """
    return await _normas_impl(titulo, client=_client)


@app.tool()
async def check_if_superseded(ecli: str) -> SupersededResult:
    """Check heuristically whether a ruling has been reversed by a later ruling.

    Searches CENDOJ for rulings that cite *ecli* alongside reversal language.

    Args:
        ecli: The ECLI string identifying the ruling to check.

    Returns:
        A SupersededResult with a mandatory disclaimer warning.
    """
    return await _superseded_impl(ecli, client=_client)


@app.resource('cendoj://{ecli}')
async def get_ruling_text(ecli: str) -> Ruling:
    """Fetch and cache the full text of a court ruling by ECLI.

    Downloads the ruling PDF from CENDOJ, extracts section text, and caches
    the result for 24 hours.

    Args:
        ecli: The ECLI string identifying the ruling.

    Returns:
        A Ruling with full PDF text extracted into RulingSections.
    """
    return await _document_impl(ecli, client=_client, cache=_disk_cache)


def main() -> None:
    """Entry point for the mcp-cendoj MCP server."""
    app.run()
