"""Tool: heuristic check whether a court ruling has been superseded."""

import re

from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.models import SupersededResult
from mcp_cendoj.tools.lookup import validate_ecli
from mcp_cendoj.tools.search import search_rulings

_REVERSAL_RE = re.compile(r'\b(revoca|casa\b|anula|deja\s+sin\s+efecto)', re.IGNORECASE)

_SUPERSEDED_WARNING = (
    'Citation coverage is incomplete — CENDOJ has no citation graph. '
    'Absence of results does NOT confirm validity. '
    'Spanish courts also cite by ROJ identifier and popular case name. '
    'A positive result indicates the checked ECLI co-occurs with reversal language '
    'in a later ruling snippet — NOT that the checked ruling is the direct subject '
    'of reversal. Manual verification by a qualified lawyer is required.'
)


async def check_if_superseded(ecli: str, client: CendojClient | None = None) -> SupersededResult:
    """Check heuristically whether *ecli* has been reversed by a later ruling.

    Searches CENDOJ for rulings whose snippets cite *ecli* alongside reversal
    language (revoca, casa, anula, deja sin efecto). Results are filtered to
    exclude self-references.

    Args:
        ecli: The ECLI string to check.
        client: Optional HTTP client for testing.

    Returns:
        A :class:`~mcp_cendoj.models.SupersededResult` with
        ``confidence='medium'`` and a mandatory disclaimer warning.

    Raises:
        ValueError: If the ECLI format is invalid.
        CendojNetworkError: On HTTP failures.
    """
    ecli = ecli.strip().upper()
    validate_ecli(ecli)

    try:
        results = await search_rulings(query=f'"{ecli}"', max_results=20, client=client)
    except CendojNetworkError as exc:
        if 'No results' in str(exc):
            results = []
        else:
            raise

    later = [r for r in results if (r.ecli or '').upper() != ecli]

    reversal_hits = [r for r in later if _REVERSAL_RE.search(r.snippet)]

    return SupersededResult(
        checked_ecli=ecli,
        later_rulings=later,
        citations_found=len(later),
        is_likely_superseded=len(reversal_hits) > 0,
        search_method='ecli_fulltext',
        confidence='medium',
        warning=_SUPERSEDED_WARNING,
    )
