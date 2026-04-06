"""Claude plugin / skill integration contract.

Provides a stable, code-level summary of what the mem-server supports so that
future Claude Code plugin or skill layers can adapt without coupling directly
to local memory internals.
"""

from __future__ import annotations


def plugin_capabilities() -> dict[str, bool | str]:
    return {
        "supports_skill": True,
        "supports_cli": True,
        "supports_plugin": True,
        "auth_mode": "device_token",
    }
