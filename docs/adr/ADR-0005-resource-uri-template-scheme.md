# ADR-0005: Resource URI Template Scheme for ECLI Identifiers

**Date**: 2026-04-30
**Status**: Accepted

## Context

The MCP resource template registered as `cendoj://{ecli}` is broken in production.
ECLI identifiers (e.g. `ECLI:ES:TS:2026:3898A`) contain colons as structural
separators. In the URI `cendoj://ECLI:ES:TS:2026:3898A`, the authority component
is parsed as `host:port`, where `ECLI` is the host and `ES:TS:2026:3898A` is an
invalid port number.

This fails at the **protocol layer** — Pydantic's `AnyUrl` (with
`UrlConstraints(host_required=False)`) is used directly in
`ReadResourceRequestParams.uri` in `mcp/types.py`. Any MCP client — Python,
TypeScript, or other — that sends `resources/read` with
`cendoj://ECLI:ES:TS:2026:3898A` causes the Python MCP server to fail when
deserializing the incoming JSON-RPC message into `ReadResourceRequest`. The
resource handler is therefore **unreachable** in production.

Three URI forms were tested with `Annotated[AnyUrl, UrlConstraints(host_required=False)]`:

| Form | Passes validation | `str()` output | Notes |
|------|------------------|----------------|-------|
| `cendoj://ECLI:ES:TS:2026:3898A` | ✗ invalid port | — | Current (broken) |
| `cendoj://ruling/ECLI:ES:TS:2026:3898A` | ✓ | unchanged | Colons valid in URI path |
| `cendoj:///ECLI:ES:TS:2026:3898A` | ✓ | unchanged | Empty authority (triple-slash) |
| `cendoj://ECLI%3AES%3ATS%3A2026%3A3898A` | ✓ | unchanged | Percent-encoded colons in host |

The `ResourceTemplate.matches()` regex converts `{ecli}` to `(?P<ecli>[^/]+)`,
which matches `ECLI:ES:TS:2026:3898A` since colons are not path separators.

## Decision

Change the registered template from `cendoj://{ecli}` to `cendoj://ruling/{ecli}`.

Clients call: `cendoj://ruling/ECLI:ES:TS:2026:3898A`

Rationale for this form over the alternatives:
- `cendoj://ruling/{ecli}` is the most semantically readable: "cendoj, ruling resource,
  ECLI identifier in path". The host segment `ruling` serves as a resource-type
  discriminator, allowing future sibling templates (`cendoj://search/{query}`, etc.)
  without ambiguity.
- `cendoj:///{ecli}` (empty authority) is valid RFC 3986 but unusual; some URI
  libraries and MCP clients may reject or mishandle an empty authority.
- Percent-encoding requires callers to URL-encode colons in the ECLI, breaking
  ergonomics for every MCP client and tool docstring.

The `ecli` parameter string extracted by the template regex is unchanged: the
function receives `"ECLI:ES:TS:2026:3898A"` as a plain string — no decoding needed.

## Consequences

**Positive**:
- Resource becomes reachable by all MCP clients (Python, TypeScript, other).
- `xfail` test in `test_mcp_integration.py` can be promoted to a passing test.
- No change to `get_ruling_text` function signature or business logic.
- URI structure accommodates future resource-type discriminators.

**Negative**:
- URI scheme changes from `cendoj://{ecli}` to `cendoj://ruling/{ecli}` — this is
  a breaking change to the MCP resource identifier. Since the previous form was
  never reachable (always raised a Pydantic error), no production client can have
  a working integration to break.
- `Ruling.cendoj_uri` field (stored in cache) currently holds CENDOJ's own HTTP URL,
  not this MCP URI, so no cache invalidation is required.
