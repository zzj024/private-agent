# Private Agent

> 私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手

一个从零构建的 AI Agent 项目：本地 LLM 驱动，具备长期记忆、私有知识库检索、ReAct 推理循环能力。项目采用渐进式架构演进——从最简单的意图路由开始，在实践中发现问题，学习 LangGraph ReAct 模式后重构升级。

---

## 项目演进路线

### v0.1 — 打地基：FastAPI + SQLite + LangGraph + Ollama

**目标：** 让一个本地 LLM 能保存记忆、能搜索知识库、能聊天。

最初的架构很直觉：用户发消息 → 规则判断意图（"记住xxx"→存记忆，"搜索xxx"→查知识库，其他→聊天）→ 调用对应模块 → 返回结果。

```
用户输入 → detect_intent（规则 + LLM 兜底）→ 路由到 chat / remember / search → 生成回答
```

**v0.1 技术栈：**
- FastAPI 提供 REST API
- LangGraph 管理对话工作流（意图检测 → 路由 → 生成）
- SQLite 存储长期记忆和会话历史
- ChromaDB 向量库存储知识库文档
- Ollama 本地运行 Qwen2.5:7b

**v0.1 暴露的问题：**

在完成 v0.1 并运行了一段时间后，几个架构层面的问题逐渐暴露出来：

1. **意图检测不可靠。** `detect_intent` 节点让 LLM 输出一个模糊的 `intent` 字符串（`"chat"` / `"remember"` / `"search"`），再用 if-else 路由。Qwen2.5:7b 的指令跟随能力有限，JSON 输出经常解析失败——模型可能返回 `"chat "`（多一个空格）或 `"我要聊天"`（整句话），case 匹配直接失效。

2. **双管线导致行为不一致。** `/chat`（同步返回 JSON）和 `/chat/stream`（SSE 流式输出）是两条完全独立的代码路径，各自构建 LangGraph 输入、各自调用 agent、各自处理错误。修一个 bug 要改两处，而且两边的 SSE 事件格式不统一。

3. **不支持删除记忆。** 用户只能存不能删，一旦记错了纠正不了。

4. **模型名硬编码。** `agent/graph.py` 里 `"qwen2.5:7b"` 写死，换模型要改代码。

5. **AgentState 字段定义混乱。** `state.py`、`graph.py`、`chat_service.py` 三个文件各自定义自己的 State 字段，根本对不上。

这些问题在单体 Demo 里不算什么，但当一个系统需要处理多意图（"先查 Redis 的文档，然后记住它的核心配置"）、需要稳定运行、需要被前端消费时，就成了真正的架构债。

### v0.2 — 架构升级：ReAct 循环 + 工具调用 + 统一管线

**核心洞察：不要让代码猜 LLM 想干什么，让 LLM 直接告诉代码要调用哪个函数。**

在研究 LangChain 和 LangGraph 的文档后，发现了两个关键概念：

- **`@tool` 装饰器 + `bind_tools()`：** 把 Python 函数包装成 LLM 可调用的工具。LLM 不再输出字符串意图，而是输出结构化的 `tool_calls`——`{"name": "search_knowledge", "args": {"query": "Redis 配置"}}`。代码只需要执行它，不需要解析它。
- **`create_react_agent`：** LangGraph 提供的预构建 ReAct（Reasoning + Acting）循环。LLM 自主决策"我需要调用工具吗？调用哪个？结果够了吗？还需要更多信息吗？"，循环直到任务完成或达到步数上限。

**v0.2 架构：**

```
用户输入
    ↓
ChatService.stream_events()     ← 统一的异步事件流（/chat 和 /chat/stream 共用）
    ↓
create_react_agent              ← LangGraph ReAct 循环
    ├─ agent 节点: LLM 决策（调用工具 or 直接回答）
    └─ tools 节点: 执行 tool_calls，结果返回 agent
         ↓
    循环直到 LLM 不再输出 tool_calls
         ↓
    SSE 事件流 → 前端消费
```

**v0.2 解决的每个问题及具体做法：**

| 问题 | v0.1 做法 | v0.2 做法 | 效果 |
|------|----------|----------|------|
| 意图检测不可靠 | LLM 输出字符串 → if-else 路由 | `@tool` 装饰 5 个函数 → `bind_tools()` → LLM 输出 `tool_calls` | 零解析，零误判 |
| 双管线不一致 | `/chat` 和 `/chat/stream` 各自实现 | `ChatService.stream_events()` 作为唯一入口，/chat 遍历收集最终结果，/chat/stream 逐条推 SSE | 一套逻辑，两种消费方式 |
| 不支持删除 | 无 | `delete_memory` + `delete_all_memories` 两个工具 | 完整 CRUD |
| 模型名硬编码 | 字符串写死 | `settings.ollama_chat_model` 从 `.env` 读取 | 换模型改配置即可 |
| State 定义混乱 | 三个文件各自定义 | 统一 `GraphState(TypedDict)`，`AgentState` 作为别名向后兼容 | 单一真相来源 |
| 错误无降级 | agent 崩溃 → 500 | `ChatService` 内 try/except 包裹，错误转为 `error` SSE 事件 | 前端可感知、可重试 |

**v0.2 的工程化成果：**

- **157 个测试**（136 单元 + 6 集成 + 7 E2E + 3 性能 + 5 安全），覆盖工具调用、API 端点、存储层、文档切块、流式协议
- **SSE 事件协议**文档化：`meta` → `stage` → `final` → `done`，前端按事件类型分发
- **ChromaDB 兼容性修复**：Windows 下 NotFoundError 替代 InvalidCollectionException，Ollama 自定义 Embedding 函数适配

### v0.3（规划中）— Reflexion 循环 + 多 Agent 审核

当前 ReAct 循环的问题是：Agent 生成回答后不会自我审查。如果一个回答引用了不存在的文档、代码有 bug、格式不对，Agent 不会发现。

**方案：** 引入 Reflexion 模式——Agent 生成回答后，由审核员（另一个 LLM 调用或同一 LLM 的审核模式）指出不足，Agent 根据反馈修正，循环直到通过或达到最大轮次。

同时规划被动记忆提取——不是等用户说"记住xxx"，而是定期分析对话历史，自动提取潜在偏好和知识。

---

## 项目结构

```
private-agent/
├── app/               # FastAPI 入口 + ChatService 统一管线
├── agent/             # LangGraph ReAct 循环 + @tool 工具定义
├── llm/               # Ollama HTTP 客户端封装
├── memory/            # SQLite 存储（记忆 + 会话 + 消息）
├── rag/               # ChromaDB 向量存储 + 文档切块 + 本地导入
├── tools/             # 知识库检索工具函数
├── config/            # Pydantic Settings 全局配置
├── knowledge/         # 本地 Markdown 笔记来源
├── tests/             # 测试套件（157 个测试）
├── static/            # 前端 HTML + SSE 客户端
└── pictures/          # 架构图
```

---

## 快速启动

```bash
# 1. 确保 Ollama 已安装并拉取模型
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 2. 启动项目
cd private-agent
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
uvicorn app.main:app --reload

# 3. 导入本地笔记到知识库
curl -X POST http://127.0.0.1:8000/ingest/local \
  -H "Content-Type: application/json" \
  -d '{"directory": "knowledge"}'

# 4. 打开浏览器 http://127.0.0.1:8000
```

---

## 核心设计

### ReAct 推理循环

使用 LangGraph 的 `create_react_agent` 构建，核心是两个节点：

- **agent 节点**：LLM（Qwen2.5:7b，temperature=0）分析用户输入，决定是否调用工具
- **tools 节点**：执行 agent 请求的 `tool_calls`，将结果返回 agent

循环持续直到 LLM 输出不包含 `tool_calls` 的消息（表示任务完成），或达到 `remaining_steps` 上限。

### 工具系统

5 个 `@tool` 装饰的函数注册为 LLM 可调用的工具：

| 工具 | 功能 | 底层操作 |
|------|------|---------|
| `search_knowledge(query)` | 搜索私有知识库 | ChromaDB 向量检索，返回 Top-5 结果 |
| `save_memory(key, value, category)` | 保存长期记忆 | SQLite INSERT OR REPLACE |
| `list_memories(category?)` | 列出记忆（可按分类筛选） | SQLite SELECT |
| `delete_memory(key)` | 删除指定记忆 | SQLite DELETE |
| `delete_all_memories()` | 删除全部记忆（需确认） | SQLite 遍历删除 |

### 统一聊天管线

`ChatService.stream_events()` 是 `/chat` 和 `/chat/stream` 的唯一业务入口——一个 `AsyncGenerator`，产出标准 SSE 事件流：

```
{"event": "meta",  "data": {"request_id": "...", "thread_id": "..."}}
{"event": "stage", "data": {"stage": "正在检索...", "message": "查找相关文档"}}
{"event": "final", "data": {"content": "根据你的知识库...", "citations": []}}
{"event": "done",  "data": {"request_id": "..."}}
```

`/chat` 遍历这个流，收集 `final` 事件后返回 JSON；`/chat/stream` 逐条包装为 `data: {json}\n\n` 格式推给前端。

### 存储层

- **SQLite**（WAL 模式）：`memories` / `conversations` / `messages` / `document_sources` / `document_updates` 五张表
- **ChromaDB**：`personal_knowledge` Collection，使用 Ollama `nomic-embed-text` 生成 768 维向量

### 文档切块策略

三级切分：先按 Markdown 标题（`##`）分割 → 超长段落按空行分割 → 超长段落按 300 字固定窗口（50 字重叠）切割。

---

## API 接口

### 聊天

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 同步聊天，返回 JSON `{"response": "..."}` |
| POST | `/chat/stream` | 流式聊天，SSE 事件流 |

### 记忆管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/memory/remember` | 保存记忆 `{key, value, category}` |
| GET | `/memory/list?category=tech_stack` | 查看记忆（可按分类筛选） |
| DELETE | `/memory/delete/{key}` | 删除指定记忆 |
| DELETE | `/memory/delete-all` | 删除全部记忆 |

### 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge/search` | 搜索知识库 `{query, top_k}` |
| POST | `/ingest/local` | 导入本地 Markdown/txt 笔记 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（含 Ollama 状态） |
| GET | `/` | 前端对话界面 |

---

## 测试

```bash
pytest tests/ -v
```

| 类型 | 数量 | 覆盖范围 |
|------|------|---------|
| 单元测试 | 136 | 工具函数、存储 CRUD、API 端点、文档切块、文本格式化、Ollama 客户端 |
| 集成测试 | 6 | Agent 管线全流程、多工具协作 |
| 端到端测试 | 7 | 完整用户对话流程、记忆增删改查、知识库搜索 |
| 性能测试 | 3 | 响应时间、并发请求 |
| 安全测试 | 5 | 空消息、超长输入、特殊字符、无效会话 ID、缺失字段 |

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | Python 3.11 + FastAPI | 异步支持，自动 OpenAPI 文档 |
| AI 框架 | LangChain + LangGraph | ReAct Agent、工具绑定、状态管理 |
| LLM | Ollama + Qwen2.5:7b | 本地运行，零 API 成本 |
| Embedding | Ollama + nomic-embed-text | 本地向量化，768 维 |
| 向量数据库 | ChromaDB | 持久化存储，余弦相似度检索 |
| 关系数据库 | SQLite (WAL) | 零配置，适合单机部署 |
| 测试 | pytest + pytest-asyncio | 异步测试支持 |

---

## 配置

```env
# .env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
CHROMA_PATH=data/chroma
SQLITE_PATH=data/agent.db
```

---

## 相关文档

- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) — v0.2 系统架构详解（含 Mermaid 图、SSE 协议定义）
- [ARCHITECTURE.md](ARCHITECTURE.md) — v0.1 原始架构规划（历史参考）
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务跟踪与修复路线图
- [AGENTS.md](AGENTS.md) — AI 协作指南

---

## 许可证

MIT License
