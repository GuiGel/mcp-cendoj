"""MCP server for the CENDOJ Spanish judicial database."""

from mcp.server.fastmcp import FastMCP

app = FastMCP('mcp-cendoj')


def main() -> None:
    """Entry point for the mcp-cendoj MCP server."""
    app.run()
