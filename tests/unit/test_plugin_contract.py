from mem0_mcp_server.plugin_contract import plugin_capabilities


def test_plugin_contract_marks_skill_and_cli_support() -> None:
    capabilities = plugin_capabilities()
    assert capabilities["supports_skill"] is True
    assert capabilities["supports_cli"] is True
    assert capabilities["auth_mode"] == "device_token"
