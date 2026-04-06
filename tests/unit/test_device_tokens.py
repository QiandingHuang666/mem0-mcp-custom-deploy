import time

from mem0_mcp_server.device_tokens import InMemoryDeviceTokenStore


def test_issue_and_verify_token() -> None:
    store = InMemoryDeviceTokenStore()
    token = store.issue_token(user_id="u1", device_id="macbook", scopes=["memory:read"])

    claims = store.verify_token(token)

    assert claims["user_id"] == "u1"
    assert claims["device_id"] == "macbook"
    assert claims["scopes"] == ["memory:read"]


def test_verify_invalid_token_returns_none() -> None:
    store = InMemoryDeviceTokenStore()

    assert store.verify_token("nonexistent") is None


def test_revoke_token() -> None:
    store = InMemoryDeviceTokenStore()
    token = store.issue_token(user_id="u1", device_id="macbook", scopes=["memory:read"])

    store.revoke_token(token)

    assert store.verify_token(token) is None


def test_expired_token_returns_none() -> None:
    store = InMemoryDeviceTokenStore()
    token = store.issue_token(user_id="u1", device_id="macbook", scopes=["memory:read"])

    # Force expiry into the past
    store._tokens[token]["expires_at"] = 0

    assert store.verify_token(token) is None
