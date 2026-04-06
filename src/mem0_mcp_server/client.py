"""Thin client for the mem-server.

Responsible only for:
- Bearer token injection
- URL construction
- Error envelope parsing
- Sending HTTP requests to the server

Does NOT contain any memory business logic.
"""

from __future__ import annotations

from typing import Any, Optional


class MemClientError(Exception):
    """Raised when the server returns a non-success response."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class MemClient:
    """Lightweight HTTP client for the mem-server."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _parse_error(self, body: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """Extract error code and detail from a response body.

        Returns ``(None, None)`` if the body does not contain an error.
        """
        if "error" in body:
            return body["error"], body.get("detail", "")
        return None, None
