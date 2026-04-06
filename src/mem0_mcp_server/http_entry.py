"""Production HTTP entry point."""

from __future__ import annotations

import os

from .server import ENV_DEFAULT_USER_ID, create_server, is_memory_adapter_initialized


def healthz() -> dict[str, str]:
    """Minimal liveness contract for HTTP mode."""
    return {"status": "ok"}


def readyz() -> dict[str, str | bool]:
    """Minimal readiness contract for HTTP mode without initializing dependencies."""
    return {
        "status": "ready",
        "auth_mode": "device_token",
        "default_user_id": ENV_DEFAULT_USER_ID,
        "memory_adapter_initialized": is_memory_adapter_initialized(),
    }


def main() -> None:
    server = create_server()
    server.settings.host = os.getenv("MCP_HOST", server.settings.host)
    server.settings.port = int(os.getenv("MCP_PORT", server.settings.port or "8081"))
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
