from mem0_mcp_server.identity import DeviceIdentity, resolve_request_identity


def test_resolve_identity_from_token_claims() -> None:
    identity = resolve_request_identity(
        token_claims={"user_id": "u1", "device_id": "d1", "scopes": ["memory:read"]},
        default_user_id="fallback",
    )
    assert identity.user_id == "u1"
    assert identity.device_id == "d1"
    assert identity.scopes == ["memory:read"]


def test_resolve_identity_falls_back_to_default() -> None:
    identity = resolve_request_identity(
        token_claims=None,
        default_user_id="fallback",
    )
    assert identity.user_id == "fallback"
    assert identity.device_id is None
    assert identity.scopes == []


def test_resolve_identity_uses_default_when_claims_missing_user_id() -> None:
    identity = resolve_request_identity(
        token_claims={"device_id": "d1"},
        default_user_id="fallback",
    )
    assert identity.user_id == "fallback"
