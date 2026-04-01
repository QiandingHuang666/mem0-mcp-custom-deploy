"""Local Memory adapter -- wraps local mem0 Memory instance to provide
the same interface as mem0.MemoryClient (cloud REST API).

This allows the MCP server code to call client.add / client.search / ...
unchanged while we route everything through a local GLM + Ollama + Qdrant
stack configured in config.py.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mem0_mcp_server.local_memory")

# ---------------------------------------------------------------------------
# Lazy singleton for the local Memory instance
# ---------------------------------------------------------------------------
_memory_instance: Optional[Any] = None


def _get_memory() -> Any:
    """Return (and lazily create) the singleton local Memory."""
    global _memory_instance
    if _memory_instance is not None:
        return _memory_instance

    # Ensure the project root is on sys.path so ``config`` can be imported
    # regardless of the working directory.
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from config import memory  # type: ignore[import-untyped]

    _memory_instance = memory
    logger.info("Local Memory instance initialized (GLM + Ollama + Qdrant)")
    return _memory_instance


# ---------------------------------------------------------------------------
# Helper: extract user_id from the nested filter dict that MemoryClient uses
# ---------------------------------------------------------------------------


def _extract_user_id_from_filters(
    filters: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Try to pull a top-level ``user_id`` out of a MemoryClient-style filter
    dict (``{"AND": [{"user_id": "..."}]}`` or ``{"user_id": "..."}``).
    """
    if not filters:
        return None

    # Direct top-level key
    if "user_id" in filters:
        return filters["user_id"]

    # Walk AND / OR lists
    for key in ("AND", "OR"):
        clause = filters.get(key)
        if isinstance(clause, list):
            for item in clause:
                if isinstance(item, dict) and "user_id" in item:
                    return item["user_id"]

    return None


def _extract_agent_id_from_filters(
    filters: Optional[Dict[str, Any]],
) -> Optional[str]:
    if not filters:
        return None
    if "agent_id" in filters:
        return filters["agent_id"]
    for key in ("AND", "OR"):
        clause = filters.get(key)
        if isinstance(clause, list):
            for item in clause:
                if isinstance(item, dict) and "agent_id" in item:
                    return item["agent_id"]
    return None


def _extract_run_id_from_filters(
    filters: Optional[Dict[str, Any]],
) -> Optional[str]:
    if not filters:
        return None
    if "run_id" in filters:
        return filters["run_id"]
    for key in ("AND", "OR"):
        clause = filters.get(key)
        if isinstance(clause, list):
            for item in clause:
                if isinstance(item, dict) and "run_id" in item:
                    return item["run_id"]
    return None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class LocalMemoryAdapter:
    """Drop-in replacement for ``mem0.MemoryClient`` that delegates to a
    local ``mem0.Memory`` instance.

    API differences handled internally:
    * ``add``        -- conversation list -> messages string / list
    * ``update``     -- ``text`` param -> ``data`` param
    * ``search``     -- filters -> extract user_id / agent_id / run_id
    * ``get_all``    -- filters -> extract user_id; manual pagination
    * ``users``      -- not natively supported, returns default user
    * ``delete_users``-- mapped to ``delete_all``
    """

    # ---- add ---------------------------------------------------------------

    def add(
        self,
        conversation: List[Dict[str, str]],
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        app_id: Optional[str] = None,
        enable_graph: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Accept the same arguments as ``MemoryClient.add``.

        ``conversation`` is a list of ``{"role": ..., "content": ...}`` dicts.
        We pass it directly to ``Memory.add`` as *messages* (the local API
        accepts ``str | Dict | List[Dict]``).
        """
        memory = _get_memory()
        kwargs: Dict[str, Any] = {}
        if user_id:
            kwargs["user_id"] = user_id
        if agent_id:
            kwargs["agent_id"] = agent_id
        if run_id:
            kwargs["run_id"] = run_id
        if metadata:
            kwargs["metadata"] = metadata

        # ``enable_graph`` is ignored -- local Memory does not support it.
        result = memory.add(conversation, **kwargs)
        return result  # dict with "results"

    # ---- search ------------------------------------------------------------

    def search(
        self,
        *,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        enable_graph: Optional[bool] = None,
    ) -> Dict[str, Any]:
        memory = _get_memory()
        kwargs: Dict[str, Any] = {}

        user_id = _extract_user_id_from_filters(filters)
        agent_id = _extract_agent_id_from_filters(filters)
        run_id = _extract_run_id_from_filters(filters)

        if user_id:
            kwargs["user_id"] = user_id
        if agent_id:
            kwargs["agent_id"] = agent_id
        if run_id:
            kwargs["run_id"] = run_id
        if limit is not None:
            kwargs["limit"] = limit

        return memory.search(query, **kwargs)

    # ---- get_all -----------------------------------------------------------

    def get_all(
        self,
        *,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        enable_graph: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """List memories.  The local Memory has no built-in pagination, so we
        fetch up to ``limit`` and then slice manually.
        """
        memory = _get_memory()
        kwargs: Dict[str, Any] = {}

        user_id = _extract_user_id_from_filters(filters)
        agent_id = _extract_agent_id_from_filters(filters)
        run_id = _extract_run_id_from_filters(filters)

        if user_id:
            kwargs["user_id"] = user_id
        if agent_id:
            kwargs["agent_id"] = agent_id
        if run_id:
            kwargs["run_id"] = run_id

        # Fetch a generous batch; the local API default is 100.
        result = memory.get_all(**kwargs)
        all_results = result.get("results", []) if isinstance(result, dict) else []

        # Manual pagination (1-indexed ``page``).
        if page is not None and page_size is not None:
            start = (page - 1) * page_size
            end = start + page_size
            all_results = all_results[start:end]

        if isinstance(result, dict):
            result["results"] = all_results
            return result
        return {"results": all_results}

    # ---- get (single memory) -----------------------------------------------

    def get(self, memory_id: str) -> Dict[str, Any]:
        memory = _get_memory()
        return memory.get(memory_id)

    # ---- update ------------------------------------------------------------

    def update(
        self,
        *,
        memory_id: str,
        text: str,
    ) -> Dict[str, Any]:
        """MemoryClient.update(memory_id=..., text=...) -> Memory.update(memory_id, data=...)."""
        memory = _get_memory()
        return memory.update(memory_id, data=text)

    # ---- delete ------------------------------------------------------------

    def delete(self, memory_id: str) -> Dict[str, Any]:
        memory = _get_memory()
        return memory.delete(memory_id)

    # ---- delete_all --------------------------------------------------------

    def delete_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        memory = _get_memory()
        kwargs: Dict[str, Any] = {}
        if user_id:
            kwargs["user_id"] = user_id
        if agent_id:
            kwargs["agent_id"] = agent_id
        if run_id:
            kwargs["run_id"] = run_id
        return memory.delete_all(**kwargs)

    # ---- users (compatibility stub) ----------------------------------------

    def users(self) -> List[Dict[str, Any]]:
        """The local Memory does not maintain a separate user registry.
        Return a sensible default so callers don't break.
        """
        default_user = os.getenv("MEM0_DEFAULT_USER_ID", "mem0-mcp")
        return [{"id": default_user, "name": default_user}]

    # ---- delete_users (maps to delete_all) ---------------------------------

    def delete_users(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        app_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The local Memory has no separate user entity; deleting a "user"
        simply removes all of its memories.
        ``app_id`` is ignored (local Memory doesn't use it).
        """
        return self.delete_all(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
        )

    # ---- history (bonus -- MemoryClient doesn't have this but local does) ---

    def history(self, memory_id: str) -> List[Any]:
        memory = _get_memory()
        return memory.history(memory_id)
