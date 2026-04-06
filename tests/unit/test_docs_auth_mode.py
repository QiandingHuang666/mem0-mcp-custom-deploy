from pathlib import Path


def test_readme_mentions_device_token_auth() -> None:
    assert "device token" in Path("README.md").read_text().lower()
