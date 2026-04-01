"""Production HTTP entry point."""

from __future__ import annotations

import os

from .server import create_server


def main() -> None:
    server = create_server()
    server.settings.host = os.getenv("MCP_HOST", server.settings.host)
    server.settings.port = int(os.getenv("MCP_PORT", server.settings.port or "8081"))
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
