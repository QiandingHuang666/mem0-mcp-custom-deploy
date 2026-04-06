"""MCP server that exposes local Mem0 operations as MCP tools.

Based on the original mem0-mcp server but adapted to use a local Memory
instance (via LocalMemoryAdapter) instead of the cloud MemoryClient.
Optionally integrates OAuth 2.1 authentication via an in-memory provider.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Annotated, Any, Dict, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from .device_tokens import InMemoryDeviceTokenStore
from .identity import DeviceIdentity, resolve_request_identity
from .local_memory import LocalMemoryAdapter
from .schemas import (
    AddMemoryArgs,
    DeleteAllArgs,
    DeleteEntitiesArgs,
    GetMemoriesArgs,
    SearchMemoriesArgs,
    ToolMessage,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("mem0_mcp_server")

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

ENV_DEFAULT_USER_ID = os.getenv("MEM0_DEFAULT_USER_ID", "mem0-mcp")
ENV_OAUTH_DISABLED = os.getenv("OAUTH_DISABLED", "true").lower() in {"1", "true", "yes"}
ENV_OAUTH_ISSUER_URL = os.getenv("OAUTH_ISSUER_URL", "http://localhost:8081")
ENV_MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8081")

# ---------------------------------------------------------------------------
# Global memory adapter (shared across all tool calls)
# ---------------------------------------------------------------------------

_memory_adapter: LocalMemoryAdapter | None = None
_device_token_store: InMemoryDeviceTokenStore | None = None


def _get_adapter() -> LocalMemoryAdapter:
    global _memory_adapter
    if _memory_adapter is None:
        _memory_adapter = LocalMemoryAdapter()
    return _memory_adapter


def _get_device_token_store() -> InMemoryDeviceTokenStore:
    global _device_token_store
    if _device_token_store is None:
        _device_token_store = InMemoryDeviceTokenStore()
    return _device_token_store


def is_memory_adapter_initialized() -> bool:
    """Report whether the shared adapter has been initialized."""
    return _memory_adapter is not None


def _resolve_context_identity(
    ctx: Context | None,
    token_store: InMemoryDeviceTokenStore,
    default_user_id: str,
) -> DeviceIdentity:
    """Resolve caller identity from Bearer token when available.

    Falls back to ``default_user_id`` when there is no request context, no
    Authorization header, or the token is invalid.
    """
    if ctx is None:
        return resolve_request_identity(None, default_user_id)

    try:
        request = ctx.request_context.request
        headers = getattr(request, "headers", None)
        auth_header = headers.get("authorization") if headers else None
    except Exception:
        auth_header = None

    if not auth_header or not auth_header.lower().startswith("bearer "):
        return resolve_request_identity(None, default_user_id)

    token = auth_header.split(" ", 1)[1].strip()
    claims = token_store.verify_token(token)
    return resolve_request_identity(claims, default_user_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with_default_filters(
    default_user_id: str, filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Ensure filters exist and include the default user_id at the top level."""
    if not filters:
        return {"AND": [{"user_id": default_user_id}]}
    if not any(key in filters for key in ("AND", "OR", "NOT")):
        filters = {"AND": [filters]}
    has_user = json.dumps(filters, sort_keys=True).find('"user_id"') != -1
    if not has_user:
        and_list = filters.setdefault("AND", [])
        if not isinstance(and_list, list):
            raise ValueError("filters['AND'] must be a list when present.")
        and_list.insert(0, {"user_id": default_user_id})
    return filters


def _with_enforced_user_filter(
    user_id: str,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Force all searches/lists to stay within the authenticated user's scope.

    Unlike `_with_default_filters`, this does not merely inject a user_id when one
    is missing — it wraps any caller-supplied filters under a top-level AND with the
    authenticated `user_id`, preventing the caller from widening scope to other users.
    """
    if not filters:
        return {"AND": [{"user_id": user_id}]}

    normalized = filters
    if not any(key in normalized for key in ("AND", "OR", "NOT")):
        normalized = {"AND": [normalized]}

    return {"AND": [{"user_id": user_id}, normalized]}


def _memory_belongs_to_user(memory: Any, user_id: str) -> bool:
    """Check whether a retrieved memory belongs to the resolved user scope."""
    if not isinstance(memory, dict):
        return False
    return memory.get("user_id") == user_id


def _scoped_memory_lookup(
    adapter: LocalMemoryAdapter,
    memory_id: str,
    identity: DeviceIdentity,
) -> Dict[str, Any] | None:
    """Fetch a memory by id and reject cross-user access."""
    memory = adapter.get(memory_id)
    if memory is None:
        return None
    if not _memory_belongs_to_user(memory, identity.user_id):
        raise PermissionError("memory_not_in_user_scope")
    return memory


def _mem0_call(func, *args, **kwargs) -> str:
    """Call a LocalMemoryAdapter method and serialize the result as JSON."""
    t0 = time.perf_counter()
    try:
        result = func(*args, **kwargs)
    except Exception as exc:
        dt = time.perf_counter() - t0
        logger.error("Memory call failed (%.3fs): %s", dt, exc)
        return json.dumps(
            {"error": str(exc)},
            ensure_ascii=False,
        )
    dt = time.perf_counter() - t0
    logger.info("mem0_call %s took %.3fs", func.__name__ if hasattr(func, '__name__') else func, dt)
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_server() -> FastMCP:
    """Create a FastMCP server using device-token authentication semantics."""

    kwargs: Dict[str, Any] = {
        "name": "mem0",
        "stateless_http": False,
        "json_response": False,
        "host": os.getenv("MCP_HOST", "0.0.0.0"),
        "port": int(os.getenv("MCP_PORT", "8081")),
    }

    logger.info("Device token authentication enabled at application layer")
    server = FastMCP(**kwargs)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @server.tool(
        description="Store a new preference, fact, or conversation snippet. "
        "Requires at least one: user_id, agent_id, or run_id."
    )
    def add_memory(
        text: Annotated[
            str,
            Field(
                description="Plain sentence summarizing what to store. "
                "Required even if `messages` is provided."
            ),
        ],
        messages: Annotated[
            Optional[list[Dict[str, str]]],
            Field(
                default=None,
                description="Structured conversation history with `role`/`content`. "
                "Use when you have multiple turns.",
            ),
        ] = None,
        user_id: Annotated[
            Optional[str],
            Field(default=None, description="Override the default user scope for this write."),
        ] = None,
        agent_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional agent identifier."),
        ] = None,
        app_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional app identifier."),
        ] = None,
        run_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional run identifier."),
        ] = None,
        metadata: Annotated[
            Optional[Dict[str, Any]],
            Field(default=None, description="Attach arbitrary metadata JSON to the memory."),
        ] = None,
        enable_graph: Annotated[
            Optional[bool],
            Field(
                default=None,
                description="Set true only if the caller explicitly wants Mem0 graph memory.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> str:
        """Write durable information to Mem0."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        args = AddMemoryArgs(
            text=text,
            messages=[ToolMessage(**msg) for msg in messages] if messages else None,
            user_id=identity.user_id if not (agent_id or run_id) else None,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
            metadata=metadata,
            enable_graph=enable_graph or False,
        )
        payload = args.model_dump(exclude_none=True)
        conversation = payload.pop("messages", None)
        if not conversation:
            derived_text = payload.pop("text", None)
            if derived_text:
                conversation = [{"role": "user", "content": derived_text}]
            else:
                return json.dumps(
                    {
                        "error": "messages_missing",
                        "detail": "Provide either `text` or `messages` so Mem0 knows what to store.",
                    },
                    ensure_ascii=False,
                )
        else:
            payload.pop("text", None)

        # Remove args that LocalMemoryAdapter.add does not accept
        payload.pop("enable_graph", None)
        payload.pop("app_id", None)

        adapter = _get_adapter()
        return _mem0_call(adapter.add, conversation, **payload)

    @server.tool(
        description="""Run a semantic search over existing memories.

Use filters to narrow results. Common filter patterns:
- Single user: {"AND": [{"user_id": "john"}]}
- Agent memories: {"AND": [{"agent_id": "agent_name"}]}
- Recent memories: {"AND": [{"user_id": "john"}, {"created_at": {"gte": "2024-01-01"}}]}
- Multiple users: {"AND": [{"user_id": {"in": ["john", "jane"]}}]}
- Cross-entity: {"OR": [{"user_id": "john"}, {"agent_id": "agent_name"}]}

user_id is automatically added to filters if not provided.
"""
    )
    def search_memories(
        query: Annotated[str, Field(description="Natural language description of what to find.")],
        filters: Annotated[
            Optional[Dict[str, Any]],
            Field(
                default=None,
                description="Additional filter clauses (user_id injected automatically).",
            ),
        ] = None,
        limit: Annotated[
            Optional[int], Field(default=None, description="Maximum number of results to return.")
        ] = None,
        enable_graph: Annotated[
            Optional[bool],
            Field(
                default=None,
                description="Set true only when the user explicitly wants graph-derived memories.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> str:
        """Semantic search against existing memories."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        args = SearchMemoriesArgs(
            query=query,
            filters=filters,
            limit=limit,
            enable_graph=enable_graph or False,
        )
        payload = args.model_dump(exclude_none=True)
        payload["filters"] = _with_enforced_user_filter(identity.user_id, payload.get("filters"))
        # Remove args that LocalMemoryAdapter.search does not accept
        payload.pop("enable_graph", None)

        adapter = _get_adapter()
        return _mem0_call(adapter.search, **payload)

    @server.tool(
        description="""Page through memories using filters instead of search.

Use filters to list specific memories. Common filter patterns:
- Single user: {"AND": [{"user_id": "john"}]}
- Agent memories: {"AND": [{"agent_id": "agent_name"}]}
- Recent memories: {"AND": [{"user_id": "john"}, {"created_at": {"gte": "2024-01-01"}}]}
- Multiple users: {"AND": [{"user_id": {"in": ["john", "jane"]}}]}

Pagination: Use page (1-indexed) and page_size for browsing results.
user_id is automatically added to filters if not provided.
"""
    )
    def get_memories(
        filters: Annotated[
            Optional[Dict[str, Any]],
            Field(
                default=None,
                description="Structured filters; user_id injected automatically.",
            ),
        ] = None,
        page: Annotated[
            Optional[int], Field(default=None, description="1-indexed page number when paginating.")
        ] = None,
        page_size: Annotated[
            Optional[int],
            Field(default=None, description="Number of memories per page (default 10)."),
        ] = None,
        enable_graph: Annotated[
            Optional[bool],
            Field(
                default=None,
                description="Set true only if the caller explicitly wants graph-derived memories.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> str:
        """List memories via structured filters or pagination."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        args = GetMemoriesArgs(
            filters=filters,
            page=page,
            page_size=page_size,
            enable_graph=enable_graph or False,
        )
        payload = args.model_dump(exclude_none=True)
        payload["filters"] = _with_enforced_user_filter(identity.user_id, payload.get("filters"))
        # Remove args that LocalMemoryAdapter.get_all does not accept
        payload.pop("enable_graph", None)

        adapter = _get_adapter()
        return _mem0_call(adapter.get_all, **payload)

    @server.tool(
        description="Delete every memory in the given user/agent/app/run but keep the entity."
    )
    def delete_all_memories(
        user_id: Annotated[
            Optional[str],
            Field(default=None, description="User scope to delete; defaults to server user."),
        ] = None,
        agent_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional agent scope to delete."),
        ] = None,
        app_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional app scope to delete."),
        ] = None,
        run_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional run scope to delete."),
        ] = None,
        ctx: Context | None = None,
    ) -> str:
        """Bulk-delete every memory in the confirmed scope."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        args = DeleteAllArgs(
            user_id=identity.user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        payload = args.model_dump(exclude_none=True)
        payload.pop("app_id", None)

        adapter = _get_adapter()
        return _mem0_call(adapter.delete_all, **payload)

    @server.tool(description="List which users/agents/apps/runs currently hold memories.")
    def list_entities(ctx: Context | None = None) -> str:
        """List entities only for the resolved caller scope."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        adapter = _get_adapter()
        return _mem0_call(adapter.users, user_id=identity.user_id)

    @server.tool(description="Fetch a single memory once you know its memory_id.")
    def get_memory(
        memory_id: Annotated[str, Field(description="Exact memory_id to fetch.")],
        ctx: Context | None = None,
    ) -> str:
        """Retrieve a single memory once the user has picked an exact ID."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        adapter = _get_adapter()
        return _mem0_call(_scoped_memory_lookup, adapter, memory_id, identity)

    @server.tool(description="Overwrite an existing memory's text.")
    def update_memory(
        memory_id: Annotated[str, Field(description="Exact memory_id to overwrite.")],
        text: Annotated[str, Field(description="Replacement text for the memory.")],
        ctx: Context | None = None,
    ) -> str:
        """Overwrite an existing memory's text after the user confirms the exact memory_id."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        adapter = _get_adapter()
        lookup_result = _mem0_call(_scoped_memory_lookup, adapter, memory_id, identity)
        if json.loads(lookup_result) is None:
            return lookup_result
        if "\"error\"" in lookup_result:
            return lookup_result
        return _mem0_call(adapter.update, memory_id=memory_id, text=text)

    @server.tool(description="Delete one memory after the user confirms its memory_id.")
    def delete_memory(
        memory_id: Annotated[str, Field(description="Exact memory_id to delete.")],
        ctx: Context | None = None,
    ) -> str:
        """Delete a memory once the user explicitly confirms the memory_id to remove."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        adapter = _get_adapter()
        lookup_result = _mem0_call(_scoped_memory_lookup, adapter, memory_id, identity)
        if json.loads(lookup_result) is None:
            return lookup_result
        if "\"error\"" in lookup_result:
            return lookup_result
        return _mem0_call(adapter.delete, memory_id)

    @server.tool(
        description="Remove the resolved user/agent/run scope entirely (and cascade-delete its memories)."
    )
    def delete_entities(
        user_id: Annotated[
            Optional[str],
            Field(default=None, description="Ignored; deletion is always scoped to the resolved user."),
        ] = None,
        agent_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional agent scope within the resolved user."),
        ] = None,
        app_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional app scope (ignored by local memory backend)."),
        ] = None,
        run_id: Annotated[
            Optional[str],
            Field(default=None, description="Optional run scope within the resolved user."),
        ] = None,
        ctx: Context | None = None,
    ) -> str:
        """Delete only entities within the resolved user's scope."""

        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        args = DeleteEntitiesArgs(
            user_id=identity.user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        if not any([args.user_id, args.agent_id, args.app_id, args.run_id]):
            return json.dumps(
                {
                    "error": "scope_missing",
                    "detail": "Provide user_id, agent_id, app_id, or run_id before calling delete_entities.",
                },
                ensure_ascii=False,
            )
        payload = args.model_dump(exclude_none=True)
        payload.pop("app_id", None)

        adapter = _get_adapter()
        return _mem0_call(adapter.delete_users, **payload)

    # ------------------------------------------------------------------
    # Identity & Capability tools
    # ------------------------------------------------------------------

    @server.tool(description="Return the identity of the current caller.")
    def whoami(ctx: Context | None = None) -> str:
        """Return the resolved identity (user_id, device_id) of the caller."""
        identity = _resolve_context_identity(ctx, _get_device_token_store(), ENV_DEFAULT_USER_ID)
        return json.dumps(
            {"user_id": identity.user_id, "device_id": identity.device_id},
            ensure_ascii=False,
        )

    @server.tool(description="Return the capabilities and configuration summary of this server.")
    def get_server_capabilities(ctx: Context | None = None) -> str:
        """Return a summary of what this server supports."""
        return json.dumps(
            {
                "auth_mode": "device_token",
                "supports_cli": True,
                "supports_plugin": True,
                "supports_skill": True,
                "default_user_id": ENV_DEFAULT_USER_ID,
                "memory_adapter_initialized": _memory_adapter is not None,
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    @server.prompt()
    def memory_assistant() -> str:
        """Get help with memory operations and best practices."""
        return """You are using the Mem0 MCP server for long-term memory management.

Quick Start:
1. Store memories: Use add_memory to save facts, preferences, or conversations
2. Search memories: Use search_memories for semantic queries
3. List memories: Use get_memories for filtered browsing
4. Update/Delete: Use update_memory and delete_memory for modifications

Filter Examples:
- User memories: {"AND": [{"user_id": "john"}]}
- Agent memories: {"AND": [{"agent_id": "agent_name"}]}
- Recent only: {"AND": [{"user_id": "john"}, {"created_at": {"gte": "2024-01-01"}}]}

Tips:
- user_id is automatically added to filters
- Use "*" as wildcard for any non-null value
- Combine filters with AND/OR/NOT for complex queries"""

    return server


def main() -> None:
    """Run the MCP server over stdio."""

    server = create_server()
    logger.info("Starting Mem0 MCP server (default user=%s)", ENV_DEFAULT_USER_ID)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
