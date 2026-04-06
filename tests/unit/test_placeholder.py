from pathlib import Path


def test_source_package_exists() -> None:
    assert Path("src/mem0_mcp_server/server.py").exists()
