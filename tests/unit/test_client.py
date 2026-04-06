from mem0_mcp_server.client import MemClient


def test_client_builds_bearer_headers() -> None:
    client = MemClient(base_url="https://mem.example.com", token="abc")
    headers = client._headers()

    assert headers["Authorization"] == "Bearer abc"
    assert headers["Content-Type"] == "application/json"


def test_client_builds_url() -> None:
    client = MemClient(base_url="https://mem.example.com", token="abc")
    url = client._url("/memories/search")

    assert url == "https://mem.example.com/memories/search"


def test_client_builds_url_strips_trailing_slash() -> None:
    client = MemClient(base_url="https://mem.example.com/", token="abc")
    url = client._url("/memories/search")

    assert url == "https://mem.example.com/memories/search"


def test_client_parse_error_envelope() -> None:
    client = MemClient(base_url="https://mem.example.com", token="abc")

    error_body = {"error": "UNAUTHORIZED", "detail": "invalid token"}
    code, detail = client._parse_error(error_body)

    assert code == "UNAUTHORIZED"
    assert detail == "invalid token"


def test_client_parse_success_envelope() -> None:
    client = MemClient(base_url="https://mem.example.com", token="abc")

    code, detail = client._parse_error({"results": []})

    assert code is None
    assert detail is None
