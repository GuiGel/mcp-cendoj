"""Tool: heuristic check whether a court ruling has been superseded."""

import re

from mcp_cendoj.http import CendojClient, CendojNetworkError
from mcp_cendoj.models import SupersededResult
from mcp_cendoj.tools.lookup import validate_ecli
from mcp_cendoj.tools.search import search_rulings

_REVERSAL_RE = re.compile(r'\b(revoca|casa\b|anula|deja\s+sin\s+efecto)', re.IGNORECASE)
"""Regex matching Spanish judicial reversal language in snippet text.

Captures the following Spanish legal terms:
    revoca: revokes / reverses (e.g. "revoca la sentencia recurrida")
    casa: cassates (e.g. "casa y anula la sentencia") — word-boundary anchored
        to avoid false matches on "casación"
    anula: annuls (e.g. "anula la decisión")
    deja sin efecto: nullifies / voids (e.g. "deja sin efecto el fallo")

Used to test whether a later-ruling snippet references the checked ECLI
alongside reversal language. A match is necessary but not sufficient to
conclude the checked ruling has actually been overturned (hence confidence='medium').
"""

_SUPERSEDED_WARNING = (
    'Citation coverage is incomplete — CENDOJ has no citation graph. '
    'Absence of results does NOT confirm validity. '
    'Spanish courts also cite by ROJ identifier and popular case name. '
    'A positive result indicates the checked ECLI co-occurs with reversal language '
    'in a later ruling snippet — NOT that the checked ruling is the direct subject '
    'of reversal. Manual verification by a qualified lawyer is required.'
)
"""Mandatory disclaimer included in every SupersededResult response.

CENDOJ does not provide a citation graph. The superseded check is purely
heuristic: snippet-level keyword matching via _REVERSAL_RE. This warning
ensures users understand that a ``is_likely_superseded=False`` result does
not confirm the ruling is still good law.
"""


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
