import os

from mem0_mcp_server.server_config import load_server_config, ServerConfig


def test_load_server_config_reads_global_llm_and_embedding() -> None:
    env = {
        "ZHIPUAI_API_KEY": "k",
        "MEM0_LLM_PROVIDER": "openai",
        "MEM0_LLM_MODEL": "glm-4.7",
        "MEM0_LLM_BASE_URL": "https://example.com/v1",
        "MEM0_EMBEDDER_PROVIDER": "ollama",
        "MEM0_EMBEDDER_MODEL": "nomic-embed-text",
        "MEM0_EMBEDDER_BASE_URL": "http://localhost:11434",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
    }
    config = load_server_config(env)

    assert isinstance(config, ServerConfig)
    assert config.llm_provider == "openai"
    assert config.llm_model == "glm-4.7"
    assert config.llm_endpoint == "https://example.com/v1"
    assert config.embedding_provider == "ollama"
    assert config.embedding_model == "nomic-embed-text"
    assert config.embedding_endpoint == "http://localhost:11434"


def test_load_server_config_has_sensible_defaults() -> None:
    env = {
        "ZHIPUAI_API_KEY": "k",
    }
    config = load_server_config(env)

    assert config.llm_provider == "openai"
    assert config.llm_model == "glm-4.7"
    assert config.llm_endpoint == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert config.embedding_provider == "ollama"
    assert config.embedding_model == "nomic-embed-text"
    assert config.embedding_endpoint == "http://localhost:11434"
