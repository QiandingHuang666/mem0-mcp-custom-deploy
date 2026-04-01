import os
from mem0 import Memory

config = {
    "llm": {
        "provider": "openai",
        "config": {
            "api_key": os.environ["ZHIPUAI_API_KEY"],
            "model": "glm-4.7",
            "openai_base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
        }
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text",
            "ollama_base_url": "http://localhost:11434",
        }
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6333,
            "embedding_model_dims": 768,
        }
    }
}

memory = Memory.from_config(config)
