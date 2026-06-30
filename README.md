# Private Agent

本地 LLM 驱动的私人知识管家 —— 从零构建的 AI Agent，具备长期记忆、私有知识库检索、ReAct 推理循环能力。

---

## 项目演进

这个项目从最简单的 if-else 路由开始，在实践中遇到问题，学习新架构后重构升级。整个过程体现了从"能跑就行"到"工程化"的成长路径。

### v0.1 — 打地基

最初的架构很直觉：用户发消息，先猜他想干什么，再分发给对应模块。

```
用户输入 → detect_intent（规则 + LLM 兜底）→ chat / remember / search → 生成回答
```

**技术栈：** FastAPI + LangGraph + SQLite + ChromaDB + Ollama + Qwen2.5:7b

这版跑通后，几个问题逐渐暴露：

1. **意图检测不可靠。** LLM 被要求输出一个意图标签（"chat" / "remember"），再用 if-else 路由。但模型经常返回带空格的 "chat " 或整句中文 "我要聊天"，case 匹配直接失效。

2. **两条聊天管线各自实现。** /chat 和 /chat/stream 是两套独立代码，修 bug 要改两处，SSE 格式不统一。

3. **不支持删除记忆。** 只能存不能删。AgentState 字段在三个文件各自定义一套，互相对不上。

4. **模型名硬编码。** 换模型要改源码。Ollama 挂了直接 500，没有降级处理。

> 这些问题在 Demo 里不算什么，但系统要处理"先查 Redis 文档，然后记住它的核心配置"这种多意图、要被前端消费时，就成了真正的架构债。

### v0.2 — 架构升级

**核心思路：不要让代码猜 LLM 想干什么，让 LLM 直接告诉代码要调用哪个函数。**

研究 LangGraph 文档后学到两个关键模式：

- **@tool + bind_tools()** —— 把 Python 函数包装成 LLM 可调用的工具。LLM 不再输出模糊的字符串，而是输出结构化 tool_calls：`{"name": "search_knowledge", "args": {"query": "Redis 配置"}}`。代码只负责执行，不需要解析 LLM 的输出。

- **create_react_agent** —— LangGraph 预构建的 ReAct 循环。LLM 在循环中自主决策：需要调工具吗？调哪个？结果够吗？还需要更多吗？循环直到完成。

**新架构：**

```
ChatService.stream_events()          ← /chat 和 /chat/stream 唯一入口
        │
        ▼
create_react_agent
  ├── agent 节点：LLM 决策（直接回答 or 调用工具）
  └── tools 节点：执行 tool_calls，结果回传 agent
        │                    ▲
        └── 循环直到 LLM 不输出 tool_calls ──┘
        │
        ▼
SSE 事件流 → 前端消费
```

**v0.1 vs v0.2 对比：**

| 问题 | v0.1 | v0.2 |
|------|------|------|
| 意图检测 | LLM 输出字符串，if-else 路由 | @tool + bind_tools()，结构化 tool_calls |
| 双管线 | 两套独立代码 | ChatService.stream_events() 统一入口 |
| 记忆 CRUD | 只能存和查 | save list delete delete_all 完整 CRUD |
| 模型切换 | 源码硬编码 | .env 配置 |
| State 管理 | 三个文件各自定义 | 统一 GraphState，AgentState 别名兼容 |
| 错误处理 | 崩溃 → 500 | try/except → error SSE 事件 |
| Windows 编码 | 乱码 | UTF-8 with BOM |
| ChromaDB | 版本 API 不兼容 | NotFoundError + 自定义 Ollama Embedding |

**工程化成果：** 157 个测试（136 单元 + 6 集成 + 7 E2E + 3 性能 + 5 安全），SSE 事件协议文档化。

### v0.3 — Reflexion 循环（开发中）

当前 ReAct 的局限：Agent 不会自我审查。引用不存在的文档、格式不对都发现不了。

v0.3 引入 Reflexion 模式，包含三个核心优化：

**1. 临时缓存列表**

循环外维护缓存，Agent 查数据时先查缓存，没有再查数据库。同一次请求中重复查询直接命中缓存，减少 ChromaDB 调用，提高性能。缓存在单次请求内有效，跨请求不共享。

**2. 记录所有回答和分数**

每次循环记录回答内容、审核分数、发现问题、改进建议。核心数据结构：

```python
@dataclass
class ReflexionAttempt:
    attempt: int           # 第几次尝试
    answer: str            # Agent 的回答
    score: int             # 审核分数 (1-10)
    passed: bool           # 是否通过
    issues: List[str]      # 结构化问题列表
    suggestions: List[str] # 对应的改进建议（一对一）
    cached_data: dict      # 本次尝试使用的缓存
```

- 通过：score >= 7，返回给用户
- 连续两次分数没提升 → 提前终止，避免越改越差
- 所有尝试都失败且 score < 4 → 返回"暂时无法回答"

**3. 智能返回策略**

```
if 有通过的尝试:
    return 通过的
else:
    return 得分最高的（但 >= 最低分数线）
```

**v0.2 vs v0.3 对比：**

| 维度 | v0.2 ReAct | v0.3 Reflexion |
|------|-----------|---------------|
| 数据查询 | 每次都查数据库 | 先查缓存，再查数据库 |
| 回答记录 | 只保留最后一次 | 保留所有回答和分数 |
| 返回策略 | 返回最后一次 | 返回通过的或得分最高的 |
| 自我审查 | 无 | 审核员打分 + 结构化反馈 |
| 终止条件 | 固定步数 | 通过 / 连续无提升 / 最大轮次 |
| 可观测性 | 低 | 高（每次尝试完整记录） |

---

## 项目结构

```
private-agent/
├── app/          FastAPI 入口 · ChatService 统一管线
├── agent/        LangGraph ReAct 循环 + Reflexion 循环 · @tool 工具定义
├── tools/        知识库检索工具
├── llm/          Ollama HTTP 客户端
├── memory/       SQLite 存储（WAL 模式）
├── rag/          ChromaDB 向量库 · 文档切块 · 本地导入
├── config/       Pydantic Settings
├── knowledge/    本地 Markdown 笔记
├── tests/        157 个测试
└── static/       前端 SPA + SSE 客户端
```

---

## 快速启动

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

python -m venv venv
source venv/Scripts/activate   # Windows
pip install -r requirements.txt

curl -X POST http://127.0.0.1:8000/ingest/local \
  -H "Content-Type: application/json" \
  -d '{"directory": "knowledge"}'

uvicorn app.main:app --reload
# 浏览器打开 http://127.0.0.1:8000
```

---

## 核心设计

### ReAct 推理循环

`create_react_agent(model=ChatOllama, tools=TOOLS, state_schema=AgentState)`

- agent 节点 — LLM（Qwen2.5:7b, temperature=0）分析输入，决定直接回答还是调用工具
- tools 节点 — 执行 agent 请求的 tool_calls，结果返回 agent
- 循环直到 LLM 不再输出 tool_calls（任务完成），或达到 remaining_steps 上限

### 5 个 LLM 可调用工具

| 工具 | 参数 | 实现 |
|------|------|------|
| `search_knowledge` | `query` | ChromaDB 向量检索 Top-5 |
| `save_memory` | `key, value, category` | SQLite INSERT OR REPLACE |
| `list_memories` | `category?` | SQLite SELECT，按分类筛选 |
| `delete_memory` | `key` | SQLite DELETE |
| `delete_all_memories` | — | 遍历删除，需用户确认 |

### 统一聊天管线

`ChatService.stream_events()` 是唯一业务入口，产出标准 SSE 事件流：

```json
{"event": "meta",  "data": {"request_id": "...", "thread_id": "..."}}
{"event": "stage", "data": {"stage": "正在检索...", "message": "查找相关文档"}}
{"event": "final", "data": {"content": "根据你的知识库...", "citations": []}}
{"event": "done",  "data": {"request_id": "..."}}
```

`/chat` 遍历流收集 final 后返回 JSON；`/chat/stream` 逐条包装为 `data: {json}\n\n` 推送。

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 同步聊天，返回 JSON |
| POST | `/chat/stream` | 流式聊天，SSE 事件流 |
| POST | `/memory/remember` | 保存记忆 `{key, value, category}` |
| GET | `/memory/list` | 查看记忆 `?category=tech_stack` |
| DELETE | `/memory/delete/{key}` | 删除指定记忆 |
| DELETE | `/memory/delete-all` | 删除全部记忆 |
| POST | `/knowledge/search` | 搜索知识库 `{query, top_k}` |
| POST | `/ingest/local` | 导入本地 Markdown/txt 笔记 |
| GET | `/health` | 健康检查（含 Ollama 状态） |
| GET | `/` | 前端对话界面 |

---

## 测试

```bash
pytest tests/ -v
```

| 类型 | 数量 | 覆盖 |
|------|:----:|------|
| 单元测试 | 136 | 工具、存储 CRUD、API 端点、文档切块、文本格式化、Ollama 客户端 |
| 集成测试 | 6 | Agent 管线全流程、多工具协作 |
| E2E 测试 | 7 | 完整对话流程、记忆增删改查、知识库搜索 |
| 性能测试 | 3 | 响应时间、并发请求 |
| 安全测试 | 5 | 空消息、超长输入、特殊字符、无效会话 ID、缺失字段 |

---

## 技术栈

| 层 | 选型 | 说明 |
|:---|:-----|:-----|
| 框架 | FastAPI | 原生异步，自动 OpenAPI 文档 |
| Agent | LangChain + LangGraph | ReAct 预构建 Agent，工具绑定，状态管理 |
| LLM | Ollama · Qwen2.5:7b | 本地运行，零 API 成本 |
| Embedding | Ollama · nomic-embed-text | 768 维本地向量化 |
| 向量库 | ChromaDB | 持久化存储，余弦相似度检索 |
| 业务库 | SQLite (WAL) | 零配置，适合单机部署 |

---

## 相关文档

- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) — 系统架构详解（Mermaid 图、SSE 协议定义）
- [ARCHITECTURE.md](ARCHITECTURE.md) — v0.1 原始架构规划（历史参考）
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务跟踪与修复路线图
