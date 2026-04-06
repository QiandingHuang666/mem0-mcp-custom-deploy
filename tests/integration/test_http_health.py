import mem0_mcp_server.http_entry as http_entry


def test_http_health_contract() -> None:
    health = http_entry.healthz()
    ready = http_entry.readyz()

    assert health["status"] == "ok"
    assert ready["status"] == "ready"
    assert "auth_mode" in ready
    assert "default_user_id" in ready


def test_readyz_has_no_adapter_init_side_effect(monkeypatch) -> None:
    called = False

    def fake_is_memory_adapter_initialized() -> bool:
        nonlocal called
        called = True
        return False

    monkeypatch.setattr(http_entry, "is_memory_adapter_initialized", fake_is_memory_adapter_initialized)

    ready = http_entry.readyz()

    assert called is True
    assert ready["memory_adapter_initialized"] is False
