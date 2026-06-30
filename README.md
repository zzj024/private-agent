# Private Agent

本地 LLM 驱动的私人知识管家 —— 从零构建的 AI Agent，具备长期记忆、私有知识库检索、ReAct 推理循环能力。

![version](https://img.shields.io/badge/version-v0.2-blue) ![tests](https://img.shields.io/badge/tests-157-green) ![python](https://img.shields.io/badge/python-3.11-blue) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 项目演进

这个项目从最简单的 if-else 路由开始，在实践中遇到问题，学习新的架构模式后重构升级。下面是整个过程。

### v0.1 — 打地基

最初的架构很直觉：用户发消息，先猜他想干什么，再分发给对应模块。

```
用户输入 → detect_intent（规则 + LLM 兜底）→ chat / remember / search → 生成回答
```

**技术栈：** FastAPI + LangGraph + SQLite + ChromaDB + Ollama + Qwen2.5:7b

这版跑通后，几个问题逐渐暴露：

1. **意图检测不可靠。** LLM 被要求输出一个意图标签（`"chat"` / `"remember"`），再用 if-else 路由。但模型经常返回带空格的 `"chat "` 或整句中文 `"我要聊天"`，case 匹配直接失效。

2. **两条聊天管线各自实现。** `/chat` 和 `/chat/stream` 是两套独立代码，修 bug 要改两处，而且两边 SSE 格式不统一。

3. **不支持删除记忆。** 用户只能存不能删。AgentState 字段在三个文件里各自定义，互相对不上。

4. **模型名硬编码。** 换模型要改源码。

5. **Ollama 挂了就直接 500。** 没有降级处理。

这些问题在 Demo 里不算什么，但系统要处理多意图（"先查 Redis 文档，再记住它的配置"）、要被前端消费时，就成了架构债。

### v0.2 — 架构升级

**核心思路：不要让代码猜 LLM 想干什么，让 LLM 直接告诉代码要调用哪个函数。**

研究了 LangGraph 文档后，找到两个关键能力：

- **`@tool` + `bind_tools()`** — 把 Python 函数包装成 LLM 可调用的工具。LLM 不再输出模糊的字符串，而是输出结构化的 `tool_calls`：`{"name": "search_knowledge", "args": {"query": "Redis 配置"}}`。代码只负责执行。

- **`create_react_agent`** — LangGraph 预构建的 ReAct 循环。LLM 在循环中自主决策：需要调工具吗？调哪个？结果够吗？还需要更多吗？循环直到完成。

```
用户输入
  →
ChatService.stream_events()          ← /chat 和 /chat/stream 共用
  →
create_react_agent
  ├─ agent 节点：LLM 决策
  └─ tools 节点：执行 tool_calls
       ↑                  │
       └── 结果返回，循环 ──┘
  →
SSE 事件流 → 前端
```

**v0.1 vs v0.2 对比：**

| 问题 | v0.1 | v0.2 |
|------|------|------|
| 意图检测 | LLM 输出字符串，if-else 路由 | `@tool` + `bind_tools()`，结构化 `tool_calls` |
| 双管线 | 两套独立代码 | `ChatService.stream_events()` 统一入口 |
| CRUD | 只能存和查 | `save` `list` `delete` `delete_all` 完整 CRUD |
| 模型切换 | 源码硬编码 | `.env` 配置 `settings.ollama_chat_model` |
| State | 三个文件各自定义 | 统一 `GraphState`，`AgentState` 别名兼容 |
| 错误处理 | 崩溃 → 500 | try/except → `error` SSE 事件 |
| 编码 | Windows 乱码 | UTF-8 with BOM |
| ChromaDB | 1.5.9+ API 不兼容 | NotFoundError + 自定义 Ollama Embedding |

**工程化成果：** 157 个测试（136 单元 + 6 集成 + 7 E2E + 3 性能 + 5 安全），SSE 事件协议文档化，完整工具测试覆盖。

### v0.3 — 规划中

当前 ReAct 的局限：Agent 不会自我审查。引用错误、格式不对都发现不了。计划引入 Reflexion 模式——Agent 生成回答 → 审核员指正 → Agent 修正 → 循环直到通过。

---

## 项目结构

```
private-agent/
├── app/          FastAPI 入口 · ChatService 统一管线
├── agent/        LangGraph ReAct 循环 · @tool 工具定义
├── tools/        知识库检索工具
├── llm/          Ollama HTTP 客户端
├── memory/       SQLite 存储
├── rag/          ChromaDB 向量库 · 文档切块 · 本地导入
├── config/       Pydantic Settings
├── knowledge/    本地 Markdown 笔记
├── tests/        157 个测试
└── static/       前端 + SSE 客户端
```

---

## 快速启动

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

curl -X POST http://127.0.0.1:8000/ingest/local \
  -H "Content-Type: application/json" \
  -d '{"directory": "knowledge"}'

uvicorn app.main:app --reload
```

浏览器打开 `http://127.0.0.1:8000`

---

## 核心设计

### ReAct 推理循环

`create_react_agent(model=ChatOllama, tools=TOOLS, state_schema=AgentState)`

- **agent 节点** — LLM 分析输入，决定直接回答还是调用工具
- **tools 节点** — 执行 tool_calls，结果传回 agent
- 循环直到 LLM 不再输出 tool_calls，或达到步数上限

### 5 个工具

| 工具 | 参数 | 实现 |
|------|------|------|
| `search_knowledge` | `query` | ChromaDB 向量检索 Top-5 |
| `save_memory` | `key, value, category` | SQLite INSERT OR REPLACE |
| `list_memories` | `category?` | SQLite SELECT + 分类筛选 |
| `delete_memory` | `key` | SQLite DELETE |
| `delete_all_memories` | — | 遍历删除，需用户确认 |

### 统一聊天管线

`ChatService.stream_events()` 是唯一业务入口，产出标准 SSE 事件流：

```
meta  → {"request_id":"...", "thread_id":"..."}
stage → {"stage":"正在检索...", "message":"查找相关文档"}
final → {"content":"回答内容", "citations":[]}
done  → {"request_id":"..."}
```

- `/chat` 遍历流，收集 `final` 后返回 JSON
- `/chat/stream` 逐条包装为 `data: ...\n\n` 推送

### 文档切块

Markdown 文件 → 按 `##` 标题分割 → 超长段落按空行分割 → 超长段落按 300 字窗口（50 字重叠）切割。

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/chat` | 聊天（JSON） |
| `POST` | `/chat/stream` | 聊天（SSE 流） |
| `POST` | `/memory/remember` | 保存记忆 |
| `GET` | `/memory/list` | 查看记忆 |
| `DELETE` | `/memory/delete/{key}` | 删除记忆 |
| `DELETE` | `/memory/delete-all` | 删除全部 |
| `POST` | `/knowledge/search` | 搜索知识库 |
| `POST` | `/ingest/local` | 导入本地笔记 |
| `GET` | `/health` | 健康检查 |
| `GET` | `/` | 前端界面 |

---

## 测试

```bash
pytest tests/ -v
```

| 类型 | 数量 | 覆盖 |
|------|:----:|------|
| 单元 | 136 | 工具 · 存储 · API · 切块 · 格式化 · Ollama |
| 集成 | 6 | Agent 全流程 · 多工具协作 |
| E2E | 7 | 对话流程 · 记忆 CRUD · 知识库搜索 |
| 性能 | 3 | 响应时间 · 并发 |
| 安全 | 5 | 边界输入 · 注入 · 无效会话 |

---

## 技术栈

| 层 | 选型 |
|:---|:-----|
| 框架 | FastAPI |
| Agent | LangChain + LangGraph |
| LLM | Ollama · Qwen2.5:7b |
| Embedding | Ollama · nomic-embed-text |
| 向量库 | ChromaDB |
| 业务库 | SQLite (WAL) |
| 测试 | pytest + asyncio |

---

## 相关文档

- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [TECH_DEBT.md](TECH_DEBT.md)
