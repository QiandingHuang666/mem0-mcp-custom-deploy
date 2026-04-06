from mem0 import Memory

from mem0_mcp_server.server_config import load_server_config

cfg = load_server_config()

config = {
    "llm": {
        "provider": cfg.llm_provider,
        "config": {
            "api_key": cfg.llm_api_key,
            "model": cfg.llm_model,
            "openai_base_url": cfg.llm_endpoint,
        },
    },
    "embedder": {
        "provider": cfg.embedding_provider,
        "config": {
            "model": cfg.embedding_model,
            "ollama_base_url": cfg.embedding_endpoint,
        },
    },
    "vector_store": {
        "provider": cfg.vector_store_provider,
        "config": {
            "host": cfg.qdrant_host,
            "port": cfg.qdrant_port,
            "embedding_model_dims": cfg.embedding_model_dims,
        },
    },
}

memory = Memory.from_config(config)
