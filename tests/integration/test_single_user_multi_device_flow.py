from types import SimpleNamespace

from mem0_mcp_server.device_tokens import InMemoryDeviceTokenStore
from mem0_mcp_server.server import _resolve_context_identity


class DummyHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class DummyRequest:
    def __init__(self, headers):
        self.headers = headers


class DummyCtx:
    def __init__(self, headers):
        self.request_context = SimpleNamespace(request=DummyRequest(headers=headers))


def test_same_user_two_devices_share_server_identity_scope() -> None:
    store = InMemoryDeviceTokenStore()

    token_a = store.issue_token(user_id="u1", device_id="mac", scopes=["memory:read"])
    token_b = store.issue_token(user_id="u1", device_id="win", scopes=["memory:read"])

    ctx_a = DummyCtx(DummyHeaders({"authorization": f"Bearer {token_a}"}))
    ctx_b = DummyCtx(DummyHeaders({"authorization": f"Bearer {token_b}"}))

    identity_a = _resolve_context_identity(ctx_a, store, default_user_id="fallback")
    identity_b = _resolve_context_identity(ctx_b, store, default_user_id="fallback")

    assert identity_a.user_id == "u1"
    assert identity_b.user_id == "u1"
    assert identity_a.device_id == "mac"
    assert identity_b.device_id == "win"


def test_revoked_token_falls_back_to_default_identity() -> None:
    store = InMemoryDeviceTokenStore()
    token = store.issue_token(user_id="u1", device_id="mac", scopes=["memory:read"])
    ctx = DummyCtx(DummyHeaders({"authorization": f"Bearer {token}"}))

    store.revoke_token(token)
    identity = _resolve_context_identity(ctx, store, default_user_id="fallback")

    assert identity.user_id == "fallback"
