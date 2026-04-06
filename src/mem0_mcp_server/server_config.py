"""Server-level global model configuration.

Defines a single ServerConfig object that governs which LLM, embedding model,
and vector store the mem-server uses.  All devices and clients share the same
configuration — there is no per-user or per-device model override.
"""

from __future__ import annotations

import os
from typing import Mapping

from pydantic import BaseModel


class ServerConfig(BaseModel):
    llm_provider: str
    llm_model: str
    llm_endpoint: str
    llm_api_key: str = ""

    embedding_provider: str
    embedding_model: str
    embedding_endpoint: str

    vector_store_provider: str = "qdrant"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    embedding_model_dims: int = 768

    auth_mode: str = "device_token"


def load_server_config(env: Mapping[str, str] | None = None) -> ServerConfig:
    """Build a ServerConfig from environment variables.

    Accepts an optional *env* mapping so that tests can inject values without
    touching ``os.environ``.  When *env* is ``None``, falls back to
    ``os.environ``.
    """
    if env is None:
        env = os.environ

    return ServerConfig(
        llm_provider=env.get("MEM0_LLM_PROVIDER", "openai"),
        llm_model=env.get("MEM0_LLM_MODEL", "glm-4.7"),
        llm_endpoint=env.get(
            "MEM0_LLM_BASE_URL",
            "https://open.bigmodel.cn/api/coding/paas/v4",
        ),
        llm_api_key=env.get("ZHIPUAI_API_KEY", ""),
        embedding_provider=env.get("MEM0_EMBEDDER_PROVIDER", "ollama"),
        embedding_model=env.get("MEM0_EMBEDDER_MODEL", "nomic-embed-text"),
        embedding_endpoint=env.get(
            "MEM0_EMBEDDER_BASE_URL",
            "http://localhost:11434",
        ),
        qdrant_host=env.get("QDRANT_HOST", "localhost"),
        qdrant_port=int(env.get("QDRANT_PORT", "6333")),
    )
