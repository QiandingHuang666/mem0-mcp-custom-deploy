import json
from types import SimpleNamespace

from mem0_mcp_server.device_tokens import InMemoryDeviceTokenStore
from mem0_mcp_server.server import create_server


class DummyHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class DummyRequest:
    def __init__(self, headers):
        self.headers = headers


class DummyCtx:
    def __init__(self, headers):
        self.request_context = SimpleNamespace(request=DummyRequest(headers=headers))


class DummyAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.memories = {
            "m-u1": {"id": "m-u1", "user_id": "u1", "memory": "owned by u1"},
            "m-u2": {"id": "m-u2", "user_id": "u2", "memory": "owned by u2"},
        }

    def get(self, memory_id):
        self.calls.append(("get", (memory_id,), {}))
        return self.memories.get(memory_id)

    def update(self, *, memory_id, text):
        self.calls.append(("update", (), {"memory_id": memory_id, "text": text}))
        return {"id": memory_id, "memory": text}

    def delete(self, memory_id):
        self.calls.append(("delete", (memory_id,), {}))
        return {"status": "deleted"}

    def delete_users(self, **kwargs):
        self.calls.append(("delete_users", (), kwargs))
        return {"status": "deleted_all"}

    def users(self, user_id=None):
        self.calls.append(("users", (), {"user_id": user_id}))
        return [{"id": user_id, "name": user_id}]


def _tool(server, name):
    return next(tool for tool in server._tool_manager.list_tools() if tool.name == name)


def _ctx_for_user(store: InMemoryDeviceTokenStore, user_id: str) -> DummyCtx:
    token = store.issue_token(user_id=user_id, device_id=f"{user_id}-device", scopes=["memory:write"])
    return DummyCtx(DummyHeaders({"authorization": f"Bearer {token}"}))


def test_get_memory_rejects_cross_user_access(monkeypatch) -> None:
    server = create_server()
    adapter = DummyAdapter()
    store = InMemoryDeviceTokenStore()

    monkeypatch.setattr("mem0_mcp_server.server._get_adapter", lambda: adapter)
    monkeypatch.setattr("mem0_mcp_server.server._get_device_token_store", lambda: store)

    result = _tool(server, "get_memory").fn(memory_id="m-u2", ctx=_ctx_for_user(store, "u1"))

    body = json.loads(result)
    assert body["error"] == "memory_not_in_user_scope"
    assert [call[0] for call in adapter.calls] == ["get"]


def test_update_memory_rejects_cross_user_access_before_write(monkeypatch) -> None:
    server = create_server()
    adapter = DummyAdapter()
    store = InMemoryDeviceTokenStore()

    monkeypatch.setattr("mem0_mcp_server.server._get_adapter", lambda: adapter)
    monkeypatch.setattr("mem0_mcp_server.server._get_device_token_store", lambda: store)

    result = _tool(server, "update_memory").fn(
        memory_id="m-u2",
        text="changed",
        ctx=_ctx_for_user(store, "u1"),
    )

    body = json.loads(result)
    assert body["error"] == "memory_not_in_user_scope"
    assert [call[0] for call in adapter.calls] == ["get"]


def test_delete_memory_rejects_cross_user_access_before_delete(monkeypatch) -> None:
    server = create_server()
    adapter = DummyAdapter()
    store = InMemoryDeviceTokenStore()

    monkeypatch.setattr("mem0_mcp_server.server._get_adapter", lambda: adapter)
    monkeypatch.setattr("mem0_mcp_server.server._get_device_token_store", lambda: store)

    result = _tool(server, "delete_memory").fn(memory_id="m-u2", ctx=_ctx_for_user(store, "u1"))

    body = json.loads(result)
    assert body["error"] == "memory_not_in_user_scope"
    assert [call[0] for call in adapter.calls] == ["get"]


def test_delete_entities_ignores_caller_supplied_user_id(monkeypatch) -> None:
    server = create_server()
    adapter = DummyAdapter()
    store = InMemoryDeviceTokenStore()

    monkeypatch.setattr("mem0_mcp_server.server._get_adapter", lambda: adapter)
    monkeypatch.setattr("mem0_mcp_server.server._get_device_token_store", lambda: store)

    _tool(server, "delete_entities").fn(
        user_id="u2",
        agent_id="agent-a",
        ctx=_ctx_for_user(store, "u1"),
    )

    delete_users_call = adapter.calls[-1]
    assert delete_users_call[0] == "delete_users"
    assert delete_users_call[2]["user_id"] == "u1"
    assert delete_users_call[2]["agent_id"] == "agent-a"


def test_list_entities_returns_only_resolved_user_scope(monkeypatch) -> None:
    server = create_server()
    adapter = DummyAdapter()
    store = InMemoryDeviceTokenStore()

    monkeypatch.setattr("mem0_mcp_server.server._get_adapter", lambda: adapter)
    monkeypatch.setattr("mem0_mcp_server.server._get_device_token_store", lambda: store)

    result = _tool(server, "list_entities").fn(ctx=_ctx_for_user(store, "u1"))

    body = json.loads(result)
    assert body == [{"id": "u1", "name": "u1"}]
    assert adapter.calls[-1] == ("users", (), {"user_id": "u1"})
