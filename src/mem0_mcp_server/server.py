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

from .auth_server import InMemoryOAuthProvider
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


def _get_adapter() -> LocalMemoryAdapter:
    global _memory_adapter
    if _memory_adapter is None:
        _memory_adapter = LocalMemoryAdapter()
    return _memory_adapter


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
    """Create a FastMCP server with optional OAuth 2.1 authentication."""

    kwargs: Dict[str, Any] = {
        "name": "mem0",
        "stateless_http": False,
        "json_response": False,
        "host": os.getenv("MCP_HOST", "0.0.0.0"),
        "port": int(os.getenv("MCP_PORT", "8081")),
    }

    if not ENV_OAUTH_DISABLED:
        from pydantic import AnyHttpUrl

        from mcp.server.auth.settings import AuthSettings

        provider = InMemoryOAuthProvider()
        kwargs["auth_server_provider"] = provider
        kwargs["auth"] = AuthSettings(
            issuer_url=AnyHttpUrl(ENV_OAUTH_ISSUER_URL),
            resource_server_url=AnyHttpUrl(ENV_MCP_SERVER_URL),
        )
        logger.info("OAuth 2.1 authentication enabled (issuer=%s)", ENV_OAUTH_ISSUER_URL)
    else:
        logger.info("OAuth authentication disabled (OAUTH_DISABLED=true)")

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

        default_user = ENV_DEFAULT_USER_ID
        args = AddMemoryArgs(
            text=text,
            messages=[ToolMessage(**msg) for msg in messages] if messages else None,
            user_id=user_id if user_id else (default_user if not (agent_id or run_id) else None),
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

        default_user = ENV_DEFAULT_USER_ID
        args = SearchMemoriesArgs(
            query=query,
            filters=filters,
            limit=limit,
            enable_graph=enable_graph or False,
        )
        payload = args.model_dump(exclude_none=True)
        payload["filters"] = _with_default_filters(default_user, payload.get("filters"))
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

        default_user = ENV_DEFAULT_USER_ID
        args = GetMemoriesArgs(
            filters=filters,
            page=page,
            page_size=page_size,
            enable_graph=enable_graph or False,
        )
        payload = args.model_dump(exclude_none=True)
        payload["filters"] = _with_default_filters(default_user, payload.get("filters"))
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

        default_user = ENV_DEFAULT_USER_ID
        args = DeleteAllArgs(
            user_id=user_id or default_user,
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
        """List users/agents/apps/runs with stored memories."""

        adapter = _get_adapter()
        return _mem0_call(adapter.users)

    @server.tool(description="Fetch a single memory once you know its memory_id.")
    def get_memory(
        memory_id: Annotated[str, Field(description="Exact memory_id to fetch.")],
        ctx: Context | None = None,
    ) -> str:
        """Retrieve a single memory once the user has picked an exact ID."""

        adapter = _get_adapter()
        return _mem0_call(adapter.get, memory_id)

    @server.tool(description="Overwrite an existing memory's text.")
    def update_memory(
        memory_id: Annotated[str, Field(description="Exact memory_id to overwrite.")],
        text: Annotated[str, Field(description="Replacement text for the memory.")],
        ctx: Context | None = None,
    ) -> str:
        """Overwrite an existing memory's text after the user confirms the exact memory_id."""

        adapter = _get_adapter()
        return _mem0_call(adapter.update, memory_id=memory_id, text=text)

    @server.tool(description="Delete one memory after the user confirms its memory_id.")
    def delete_memory(
        memory_id: Annotated[str, Field(description="Exact memory_id to delete.")],
        ctx: Context | None = None,
    ) -> str:
        """Delete a memory once the user explicitly confirms the memory_id to remove."""

        adapter = _get_adapter()
        return _mem0_call(adapter.delete, memory_id)

    @server.tool(
        description="Remove a user/agent/app/run record entirely (and cascade-delete its memories)."
    )
    def delete_entities(
        user_id: Annotated[
            Optional[str],
            Field(default=None, description="Delete this user and its memories."),
        ] = None,
        agent_id: Annotated[
            Optional[str],
            Field(default=None, description="Delete this agent and its memories."),
        ] = None,
        app_id: Annotated[
            Optional[str],
            Field(default=None, description="Delete this app and its memories."),
        ] = None,
        run_id: Annotated[
            Optional[str],
            Field(default=None, description="Delete this run and its memories."),
        ] = None,
        ctx: Context | None = None,
    ) -> str:
        """Delete a user/agent/app/run (and its memories) once the user confirms the scope."""

        args = DeleteEntitiesArgs(
            user_id=user_id,
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
