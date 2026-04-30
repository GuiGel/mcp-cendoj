"""Tests for the search_rulings tool."""

from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from pydantic import ValidationError

from mcp_cendoj.constants import (
    CENDOJ_SEARCH_URL,
    CENDOJ_SESSION_INIT_URL,
    TIPOINTERES_VALUES,
)
from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.tools.search import search_rulings

_RESULT_TEMPLATE = """\
<div class="row searchresult doc" data-ref="{ref}" data-db="TS" data-fechares="20200615">
  <div class="col-xs-12 col-sm-11 content">
    <div class="title">
      <a href="#" data-roj="STS {ref}/2020" data-reference="{ref}" data-databasematch="TS" data-optimize="20200616">
        STS, a 15 de junio de 2020 - ROJ: STS {ref}/2020
      </a>
    </div>
    <div class="metadatos">
      <ul>
        <li><b>ECLI:ES:TS:2020:{ref}</b></li>
        <li>Sala de lo Civil</li>
      </ul>
    </div>
    <div class="summary">Snippet text for ruling {ref}.</div>
  </div>
</div>
"""

_TWO_RESULT_HTML = (
    f'<div class="resultswrapper">{_RESULT_TEMPLATE.format(ref="12345")}{_RESULT_TEMPLATE.format(ref="67890")}</div>'
)
_ZERO_RESULT_HTML = '<div class="resultswrapper"></div>'


async def test_successful_search_returns_results(make_cendoj_client: Callable[..., CendojClient]) -> None:
    client = make_cendoj_client(_TWO_RESULT_HTML)

    results = await search_rulings('tutela judicial', client=client)

    assert len(results) == 2
    assert results[0].ecli == 'ECLI:ES:TS:2020:12345'
    assert results[0].court == 'Sala de lo Civil'
    assert results[0].date == '2020-06-15'
    assert results[0].freshness == 'unknown'
    assert results[1].ecli == 'ECLI:ES:TS:2020:67890'


async def test_empty_results_raises_network_error(make_cendoj_client: Callable[..., CendojClient]) -> None:
    client = make_cendoj_client(_ZERO_RESULT_HTML)

    with pytest.raises(CendojNetworkError, match='No results'):
        await search_rulings('no match query', client=client)


async def test_max_results_clamped_to_cap() -> None:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, text=_TWO_RESULT_HTML)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_capture)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await search_rulings('query', max_results=200, client=client)
    await client.close()

    assert captured.get('recordsPerPage') == '50'


async def test_max_results_zero_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        await search_rulings('query', max_results=0)


async def test_network_error_propagates() -> None:
    def _raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('network failure', request=request)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_raise_timeout)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    with pytest.raises(CendojNetworkError):
        await search_rulings('query', client=client)
    await client.close()


async def test_filter_params_sent_in_form_body() -> None:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, text=_TWO_RESULT_HTML)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_capture)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await search_rulings(
        'despido',
        jurisdiccion='SOCIAL',
        tipo_resolucion='SENTENCIA',
        tipo_organo='14',
        idioma='1',
        fecha_desde='01/01/2020',
        fecha_hasta='31/12/2024',
        ponente='García',
        client=client,
    )
    await client.close()

    assert captured['JURISDICCION'] == 'SOCIAL'
    assert captured['SUBTIPORESOLUCION'] == 'SENTENCIA'
    assert captured['TIPOORGANOPUB'] == '14'
    assert captured['IDIOMA'] == '1'
    assert captured['FECHARESOLUCIONDESDE'] == '01/01/2020'
    assert captured['FECHARESOLUCIONHASTA'] == '31/12/2024'
    assert captured['PONENTE'] == 'García'
    assert captured['TEXT'] == 'despido'


async def test_omitted_filter_params_use_empty_defaults() -> None:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, text=_TWO_RESULT_HTML)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_capture)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))

    await search_rulings('tutela', client=client)
    await client.close()

    assert captured.get('JURISDICCION', '') == ''
    assert captured.get('SUBTIPORESOLUCION', '') == ''
    assert captured.get('TIPOORGANOPUB', '') == ''
    assert captured.get('PONENTE', '') == ''


def _make_capture_client() -> tuple[dict[str, str], CendojClient]:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, text=_TWO_RESULT_HTML)

    router = respx.Router(assert_all_mocked=True)
    router.get(CENDOJ_SESSION_INIT_URL).respond(200, text='ok')
    router.post(CENDOJ_SEARCH_URL).mock(side_effect=_capture)
    client = CendojClient(transport=httpx.MockTransport(router.async_handler))
    return captured, client


async def test_roj_and_resolution_numbers_sent_in_form_body() -> None:
    captured, client = _make_capture_client()

    await search_rulings(
        'despido',
        roj='STS 1234/2024',
        numero_resolucion='456',
        numero_recurso='789',
        client=client,
    )
    await client.close()

    assert captured['ROJ'] == 'STS 1234/2024'
    assert captured['NUMERORESOLUCION'] == '456'
    assert captured['NUMERORECURSO'] == '789'


async def test_norma_id_sent_in_form_body() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', norma_id='2015/11430', client=client)
    await client.close()

    assert captured['ID_NORMA'] == '2015/11430'


async def test_articulo_sent_in_form_body() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', norma_id='2015/11430', articulo='14', client=client)
    await client.close()

    assert captured['ID_NORMA'] == '2015/11430'
    assert captured['ARTICULO'] == '14'


async def test_comunidad_wire_format_sent_in_form_body() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', comunidad='MADRID', client=client)
    await client.close()

    assert captured['VALUESCOMUNIDAD'] == 'MADRID(C) | '


async def test_seccion_auto_sent_in_form_body() -> None:
    captured, client = _make_capture_client()

    await search_rulings('auto nulidad', seccion_auto='2', client=client)
    await client.close()

    assert captured['SECCIONAUTO'] == '2'


async def test_interest_boolean_flags_sent_as_wire_values() -> None:
    captured, client = _make_capture_client()

    await search_rulings(
        'despido',
        interes_ts=True,
        actualidad=True,
        igualdad_genero=True,
        discapacidad=True,
        lectura_facil=True,
        historico_ts=True,
        client=client,
    )
    await client.close()

    assert captured['TIPOINTERES_JURIDICO'] == TIPOINTERES_VALUES['TIPOINTERES_JURIDICO']
    assert captured['TIPOINTERES_ACTUAL'] == TIPOINTERES_VALUES['TIPOINTERES_ACTUAL']
    assert captured['TIPOINTERES_IGUALDAD'] == TIPOINTERES_VALUES['TIPOINTERES_IGUALDAD']
    assert captured['TIPOINTERES_DISCAPACIDAD'] == TIPOINTERES_VALUES['TIPOINTERES_DISCAPACIDAD']
    assert captured['TIPOINTERES_LECTURAFACIL'] == TIPOINTERES_VALUES['TIPOINTERES_LECTURAFACIL']
    assert captured['HISTORICOPUBLICO'] == TIPOINTERES_VALUES['HISTORICOPUBLICO']


async def test_interest_flags_false_keep_empty_defaults() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', interes_ts=False, historico_ts=False, client=client)
    await client.close()

    assert captured.get('TIPOINTERES_JURIDICO', '') == ''
    assert captured.get('HISTORICOPUBLICO', '') == ''


async def test_seccion_sent_in_form_body() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', seccion='3', client=client)
    await client.close()

    assert captured['SECCION'] == '3'


async def test_solo_pleno_sends_seccionsolopleno_true() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', solo_pleno=True, client=client)
    await client.close()

    assert captured['SECCIONSOLOPLENO'] == 'true'


async def test_solo_pleno_false_omits_seccionsolopleno() -> None:
    captured, client = _make_capture_client()

    await search_rulings('despido', solo_pleno=False, client=client)
    await client.close()

    assert 'SECCIONSOLOPLENO' not in captured
