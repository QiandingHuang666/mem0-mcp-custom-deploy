from mem0_mcp_server.local_memory import LocalMemoryAdapter


class DummyMemory:
    """Fake mem0.Memory that records all calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def add(self, conversation, **kwargs):
        self.calls.append((conversation, kwargs))
        return {"results": []}

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {"results": []}

    def get_all(self, **kwargs):
        self.calls.append(("", kwargs))
        return {"results": []}

    def get(self, memory_id):
        return {"id": memory_id, "memory": "test"}

    def update(self, memory_id, data):
        return {"id": memory_id, "memory": data}

    def delete(self, memory_id):
        return {"status": "deleted"}

    def delete_all(self, **kwargs):
        return {"status": "deleted_all"}


def _make_adapter(monkeypatch) -> tuple[LocalMemoryAdapter, DummyMemory]:
    dummy = DummyMemory()
    monkeypatch.setattr(
        "mem0_mcp_server.local_memory._get_memory", lambda: dummy
    )
    return LocalMemoryAdapter(), dummy


def test_add_passes_user_id(monkeypatch) -> None:
    adapter, dummy = _make_adapter(monkeypatch)
    adapter.add(
        [{"role": "user", "content": "hello"}],
        user_id="u1",
    )
    _, kwargs = dummy.calls[0]
    assert kwargs["user_id"] == "u1"


def test_add_preserves_metadata_with_device_id(monkeypatch) -> None:
    adapter, dummy = _make_adapter(monkeypatch)
    adapter.add(
        [{"role": "user", "content": "hello"}],
        user_id="u1",
        metadata={"device_id": "macbook", "source": "cli"},
    )
    _, kwargs = dummy.calls[0]
    assert kwargs["metadata"]["device_id"] == "macbook"
    assert kwargs["metadata"]["source"] == "cli"


def test_search_extracts_user_id_from_filters(monkeypatch) -> None:
    adapter, dummy = _make_adapter(monkeypatch)
    adapter.search(
        query="hello",
        filters={"AND": [{"user_id": "u1"}]},
    )
    _, kwargs = dummy.calls[0]
    assert kwargs["user_id"] == "u1"


def test_get_all_extracts_user_id_from_filters(monkeypatch) -> None:
    adapter, dummy = _make_adapter(monkeypatch)
    adapter.get_all(
        filters={"AND": [{"user_id": "u1"}]},
    )
    _, kwargs = dummy.calls[0]
    assert kwargs["user_id"] == "u1"


def test_get_all_manual_pagination(monkeypatch) -> None:
    adapter, dummy = _make_adapter(monkeypatch)
    # Return 5 fake results
    dummy.calls.clear()

    def fake_get_all(**kwargs):
        return {"results": [{"id": f"m{i}"} for i in range(5)]}

    dummy.get_all = fake_get_all
    result = adapter.get_all(
        filters={"user_id": "u1"},
        page=2,
        page_size=2,
    )
    # Page 2 of [m0,m1,m2,m3,m4] with page_size=2 → [m2,m3]
    assert len(result["results"]) == 2
    assert result["results"][0]["id"] == "m2"


def test_users_returns_only_requested_user_scope(monkeypatch) -> None:
    adapter, _ = _make_adapter(monkeypatch)

    users = adapter.users(user_id="u1")

    assert users == [{"id": "u1", "name": "u1"}]
