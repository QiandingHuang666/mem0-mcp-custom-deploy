"""Request identity model for device-token authentication.

Encapsulates the mapping from a verified token's claims to a DeviceIdentity
that server tool handlers use to determine which user's memory space to
operate on.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DeviceIdentity(BaseModel):
    user_id: str
    device_id: str | None = None
    scopes: list[str] = []


def resolve_request_identity(
    token_claims: dict[str, Any] | None,
    default_user_id: str,
) -> DeviceIdentity:
    """Derive a DeviceIdentity from token claims, falling back to *default_user_id*.

    - If *token_claims* is present and contains ``user_id``, use it.
    - Otherwise fall back to *default_user_id*.
    - ``device_id`` and ``scopes`` are carried over when present.
    """
    if token_claims and "user_id" in token_claims:
        return DeviceIdentity(
            user_id=token_claims["user_id"],
            device_id=token_claims.get("device_id"),
            scopes=token_claims.get("scopes", []),
        )
    return DeviceIdentity(user_id=default_user_id)
