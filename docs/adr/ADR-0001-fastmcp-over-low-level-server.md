# ADR-0001: Use `FastMCP` high-level API over low-level `mcp.Server`

**Date**: 2026-04-29
**Status**: Accepted

## Context

The MCP Python SDK (`mcp[cli]`) exposes two programming interfaces:

- **Low-level**: `mcp.server.Server` — explicit protocol handling, manual JSON Schema writing, lifecycle management hooks required.
- **High-level**: `mcp.server.fastmcp.FastMCP` — auto-generates tool/resource schemas from Python type annotations, handles lifecycle, and reduces setup to ~20 lines.

The existing `pyproject.toml` already defines `mcp-cendoj = "mcp_cendoj:main"` as the entry point, which `FastMCP.run()` calls directly. Starting from the CLI stub and adding low-level MCP lifecycle is harder than starting from `FastMCP` with a thin `main()` wrapper.

## Decision

Import and instantiate `FastMCP` from `mcp.server.fastmcp`. All tools, resources, and prompts are registered via `@app.tool()`, `@app.resource()`, and `@app.prompt()` decorators. `main()` calls `app.run()` with no arguments (defaults to stdio transport for MCP client compatibility).

```python
from mcp.server.fastmcp import FastMCP

app = FastMCP("mcp-cendoj")

def main() -> None:
    app.run()
```

## Consequences

**Positive**:
- Schemas auto-generated from Python type annotations — no manual JSON Schema.
- Pyright validates tool signatures at development time.
- Standard `uv run mcp dev` inspector works out of the box.
- Compatible with `uv run mcp install` for Claude Desktop registration.

**Negative**:
- Less control over low-level protocol details (acceptable for this use case).
- Tied to `mcp.server.fastmcp` module path, which may move in future SDK versions — pin `mcp[cli]>=1.0,<2`.
