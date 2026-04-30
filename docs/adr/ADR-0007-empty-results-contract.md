# ADR-0007: Empty Result Set Contract for MCP Tools

**Date**: 2026-04-30
**Status**: Accepted
**Supersedes**: ADR-0002 §Required Hardening clause 7 ("Empty result set treated as a distinct error, not a silent success")

## Context

ADR-0002 originally mandated that an empty result set from CENDOJ be raised as a
`CendojNetworkError`. The rationale at the time was scraping-safety: a query that
unexpectedly returns 0 results could indicate a silent parser failure or a server
error masquerading as an empty response.

In practice, the MCP framework surfaces any uncaught exception as a tool-level
error (`result.isError = True`), which propagates to the LLM caller as a failure.
This is wrong UX for an over-filtered query: a user asking for rulings from a very
specific combination of filters (jurisdiction + date range + ponente + articulo)
may legitimately get zero results. The tool should return an empty list so the LLM
can say "no results found" rather than "an error occurred".

Furthermore, `CendojNetworkError` is documented in `http.py` as:
*"Raised on unrecoverable HTTP errors from the CENDOJ endpoint."*
A valid HTTP 200 with zero results is not an unrecoverable HTTP error; using
`CendojNetworkError` for this case pollutes the exception taxonomy.

## Decision

MCP search tools (`search_rulings`, `search_normas`) **return an empty list** when
the CENDOJ response is a well-formed HTTP 200 with no result entries.

`CendojNetworkError` is reserved exclusively for:
- HTTP 4xx / 5xx responses
- Network-level failures (`httpx.TimeoutException`, connection errors)
- Responses that cannot be parsed as valid HTML (malformed body)

## Consequences

**Positive**:
- LLM callers receive a clean empty list for over-filtered queries — better UX.
- `CendojNetworkError` semantics match its docstring: HTTP/network failures only.
- Simplifies the search tool implementation (no special-case raise on empty list).

**Negative / Accepted Risk**:
- A parser regression (e.g., broken CSS selector after a CENDOJ HTML restructure)
  will surface as `[]` rather than an error, making it harder to detect in
  production. Mitigation: integration tests against live HTML fixtures (mandated
  by ADR-0002) will catch selector drift; the `make test` quality gate must remain
  green before every commit.

## Scope

Applies to `search_rulings` (`src/mcp_cendoj/tools/search.py`).
`search_normas` already followed this contract prior to this ADR;
`check_if_superseded` returns a model object and is unaffected.
