"""In-memory device token store for first-version authentication.

Replaces the full OAuth 2.1 flow with a simpler device-token model:
each device receives a long-lived bearer token bound to a user_id.
The server verifies tokens on every request and resolves the identity
via ``identity.resolve_request_identity``.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Optional

_ACCESS_TOKEN_TTL = 365 * 24 * 60 * 60  # ~1 year


class InMemoryDeviceTokenStore:
    """Simple in-memory store mapping opaque tokens to identity claims."""

    def __init__(self) -> None:
        self._tokens: Dict[str, dict[str, Any]] = {}

    def issue_token(
        self,
        user_id: str,
        device_id: str,
        scopes: Optional[list[str]] = None,
    ) -> str:
        token = secrets.token_urlsafe(48)
        self._tokens[token] = {
            "user_id": user_id,
            "device_id": device_id,
            "scopes": scopes or [],
            "expires_at": time.time() + _ACCESS_TOKEN_TTL,
        }
        return token

    def verify_token(self, token: str) -> Optional[dict[str, Any]]:
        record = self._tokens.get(token)
        if record is None:
            return None
        if time.time() > record["expires_at"]:
            self._tokens.pop(token, None)
            return None
        return {
            "user_id": record["user_id"],
            "device_id": record["device_id"],
            "scopes": record["scopes"],
        }

    def revoke_token(self, token: str) -> None:
        self._tokens.pop(token, None)
