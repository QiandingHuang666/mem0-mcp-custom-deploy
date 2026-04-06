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


def test_resolve_context_identity_uses_bearer_token() -> None:
    store = InMemoryDeviceTokenStore()
    token = store.issue_token(user_id="u1", device_id="mac", scopes=["memory:read"])
    ctx = DummyCtx(DummyHeaders({"authorization": f"Bearer {token}"}))

    identity = _resolve_context_identity(ctx, store, "fallback")

    assert identity.user_id == "u1"
    assert identity.device_id == "mac"


def test_resolve_context_identity_falls_back_without_bearer() -> None:
    store = InMemoryDeviceTokenStore()
    ctx = DummyCtx(DummyHeaders({}))

    identity = _resolve_context_identity(ctx, store, "fallback")

    assert identity.user_id == "fallback"
    assert identity.device_id is None


def test_resolve_context_identity_falls_back_for_invalid_token() -> None:
    store = InMemoryDeviceTokenStore()
    ctx = DummyCtx(DummyHeaders({"authorization": "Bearer invalid"}))

    identity = _resolve_context_identity(ctx, store, "fallback")

    assert identity.user_id == "fallback"
