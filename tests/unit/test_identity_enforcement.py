from types import SimpleNamespace

from mem0_mcp_server.device_tokens import InMemoryDeviceTokenStore
from mem0_mcp_server.server import _resolve_context_identity, _with_enforced_user_filter


class DummyHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class DummyRequest:
    def __init__(self, headers):
        self.headers = headers


class DummyCtx:
    def __init__(self, headers):
        self.request_context = SimpleNamespace(request=DummyRequest(headers=headers))


def test_enforced_user_filter_overrides_explicit_user_id() -> None:
    filters = {"AND": [{"user_id": "other-user"}, {"agent_id": "a1"}]}

    enforced = _with_enforced_user_filter("u1", filters)

    assert enforced == {
        "AND": [
            {"user_id": "u1"},
            {"AND": [{"user_id": "other-user"}, {"agent_id": "a1"}]},
        ]
    }


def test_resolved_identity_must_be_used_for_writes() -> None:
    store = InMemoryDeviceTokenStore()
    token = store.issue_token(user_id="u1", device_id="mac", scopes=["memory:write"])
    ctx = DummyCtx(DummyHeaders({"authorization": f"Bearer {token}"}))

    identity = _resolve_context_identity(ctx, store, "fallback")

    requested_user_id = "other-user"
    effective_user_id = identity.user_id

    assert requested_user_id != effective_user_id
    assert effective_user_id == "u1"


def test_enforced_user_filter_adds_user_id_when_missing() -> None:
    filters = {"agent_id": "a1"}

    enforced = _with_enforced_user_filter("u1", filters)

    assert enforced == {"AND": [{"user_id": "u1"}, {"AND": [{"agent_id": "a1"}]}]}
