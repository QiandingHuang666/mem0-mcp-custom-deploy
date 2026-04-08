# mem0-mcp-custom-deploy

基于 [mem0](https://github.com/mem0ai/mem0) 和 [mem0-mcp](https://github.com/mem0ai/mem0-mcp) 的本地部署方案，将 mem0 作为 MCP Server 运行，供 Claude Code 等客户端使用。

## 架构

```
客户端 (Claude Code)                     服务主机
┌──────────────────┐    HTTP/SSE     ┌──────────────────────┐
│  MCP Client      │────────────────>│  mem0-mcp-server     │
│  (本地/远程)      │                 │  (streamable-http)   │
└──────────────────┘                 │  + Device Token Auth         │
                                     └──────────┬───────────┘
                                                │
                          ┌─────────────────────┼────────────────┐
                          │                     │                │
                    ┌─────┴─────┐        ┌──────┴──────┐  ┌─────┴─────┐
                    │  Ollama   │        │  Qdrant     │  │  GLM LLM  │
                    │  嵌入模型  │        │  向量数据库  │  │  (智谱AI)  │
                    └───────────┘        └─────────────┘  └───────────┘
```

- **LLM**: 智谱AI GLM-4.7（通过 OpenAI 兼容 API）
- **Embedder**: Ollama + nomic-embed-text（本地，768 维）
- **Vector Store**: Qdrant（本地二进制）
- **认证**: Device Token（主路径）；远程暴露时建议再配合 TLS

## 工具列表

| 工具 | 说明 |
|------|------|
| `add_memory` | 添加记忆（文本或对话历史） |
| `search_memories` | 语义搜索记忆 |
| `get_memories` | 按过滤器浏览/分页记忆 |
| `get_memory` | 按 ID 获取单条记忆 |
| `update_memory` | 更新记忆内容 |
| `delete_memory` | 删除单条记忆 |
| `delete_all_memories` | 删除指定范围所有记忆 |
| `delete_entities` | 删除用户/Agent 及其记忆 |
| `list_entities` | 列出当前存储的实体 |

## 前置依赖

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器
- [Ollama](https://ollama.com/) + `nomic-embed-text` 模型
- [Qdrant](https://qdrant.tech/) 二进制
- 智谱AI API Key

## 用户快速上手

你可以把这套系统理解成：
- `mem server` 统一保存和检索记忆
- 你的 CLI / Claude Code / 后续 plugin 只是接入入口
- 同一用户的不同设备，可以通过各自 token 访问同一份记忆

推荐按下面顺序体验：
1. 启动 server
2. 确认当前 token 对应的身份
3. 写入一条简单记忆
4. 搜索刚写入的记忆
5. 在另一台设备上验证是否能访问同一用户记忆

典型效果：
- 你在工作电脑写入的长期偏好
- 可以在家里的开发机继续使用
- server 会按 token 自动限制在当前用户范围内，不依赖调用方手工传 `user_id`

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/QiandingHuang666/mem0-mcp-custom-deploy.git
cd mem0-mcp-custom-deploy
uv sync
```

### 2. 配置环境变量

```bash
cp mem0-stack.env.example .env
```

编辑 `.env`，填入你的智谱AI API Key：

```env
ZHIPUAI_API_KEY=your-api-key-here
```

同时编辑 `config.py`，确认 LLM/Embedder/Qdrant 配置正确。

### 3. 确保 Ollama 和 Qdrant 运行

```bash
# Ollama
ollama serve &
ollama pull nomic-embed-text

# Qdrant
qdrant --storage-path ./storage &
```

### 4. 启动 MCP Server

**stdio 模式**（本地 Claude Code 直接使用）：

```bash
# device token auth is enabled by default uv run python -m mem0_mcp_server.server
```

**HTTP 模式**（供远程设备连接）：

```bash
# device token auth is enabled by default MCP_PORT=8081 uv run python -m mem0_mcp_server.http_entry
```

## 配置 Claude Code

### 本地使用（stdio）

```bash
claude mcp add mem0 -- uv run --directory /path/to/mem0-mcp-custom-deploy python -m mem0_mcp_server.server
```

需在 MCP 配置中设置环境变量 `# device token auth is enabled by default`。

### 本地使用（HTTP）

```bash
# 先启动 HTTP server
# device token auth is enabled by default uv run python -m mem0_mcp_server.http_entry

# 添加 MCP 连接
claude mcp add --transport http mem0 http://localhost:8081/mcp
```

### 远程设备使用

通过云服务器反向代理暴露后，主认证仍是 device-token；若走公网，建议同时启用 TLS：

```bash
claude mcp add --transport http mem0 https://your-domain.com/mcp
```

### Claude plugin / skill 接入约定

- Claude plugin、skill 和 CLI 应共享同一个 mem server，而不是分别直连底层 `mem0` 或 `LocalMemoryAdapter`
- Claude 集成层应通过统一 client / server 契约访问能力，避免出现专有私有数据路径
- 第一阶段主认证模式为 `device token`；公网部署建议额外配合 `TLS`
- CLI、plugin、skill 都以 server 公开的 capability / identity 工具和摘要为准

## systemd 服务（统一管理）

将 Ollama + Qdrant + MCP Server 作为一个 systemd service 统一管理：

```bash
# 安装
./install-service.sh

# 编辑配置
sudo vim /etc/mem0-stack.env

# 启动
sudo systemctl start mem0-stack

# 查看日志
journalctl -u mem0-stack -f

# 开机自启
sudo systemctl enable mem0-stack
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ZHIPUAI_API_KEY` | - | 智谱AI API Key（必须） |
| `MEM0_DEFAULT_USER_ID` | `mem0-mcp` | 默认用户 ID |
| `MEM0_DEFAULT_USER_ID` | `mem0-mcp` | 默认用户 ID |
| `DEVICE_TOKEN` | - | 设备令牌（由 server 签发/管理） |
| `MCP_SERVER_URL` | `http://localhost:8081` | MCP Server URL |
| `MCP_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `MCP_PORT` | `8081` | HTTP 监听端口 |
| `QDRANT_PATH` | `./storage` | Qdrant 数据目录 |

## 项目结构

```
├── config.py                      # mem0 配置（LLM/Embedder/Qdrant）
├── src/mem0_mcp_server/
│   ├── __init__.py
│   ├── server.py                  # MCP Server 主入口
│   ├── http_entry.py              # HTTP 模式入口
│   ├── local_memory.py            # MemoryClient → Memory 适配层
│   ├── auth_server.py             # 旧 OAuth 兼容辅助模块（非主路径）
│   └── schemas.py                 # Pydantic 模型
├── mem0-stack.sh                  # systemd wrapper 脚本
├── mem0-stack.service             # systemd unit 文件
├── mem0-stack.env.example         # 环境变量模板
├── install-service.sh             # 一键安装脚本
└── pyproject.toml
```

## License

Apache-2.0
