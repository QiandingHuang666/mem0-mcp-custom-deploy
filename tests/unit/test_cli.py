from mem0_mcp_server.cli import build_parser


def test_cli_exposes_whoami_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["whoami"])
    assert args.command == "whoami"


def test_cli_exposes_search_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["search", "hello world"])
    assert args.command == "search"
    assert args.query == "hello world"


def test_cli_exposes_add_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["add", "remember this"])
    assert args.command == "add"
    assert args.text == "remember this"


def test_cli_exposes_doctor_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"
