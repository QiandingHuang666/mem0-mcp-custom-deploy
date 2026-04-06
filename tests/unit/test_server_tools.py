from mem0_mcp_server.server import create_server


def test_server_registers_whoami_and_capability_tools() -> None:
    server = create_server()
    tool_names = {tool.name for tool in server._tool_manager.list_tools()}

    assert "whoami" in tool_names
    assert "get_server_capabilities" in tool_names
