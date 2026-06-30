<p align="center">
  <h1 align="center">Private Agent</h1>
  <p align="center"><i>本地 LLM 驱动的私人知识管家 —— 从零构建的 AI Agent 实践</i></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-v0.2-blue" alt="version">
  <img src="https://img.shields.io/badge/tests-157-green" alt="tests">
  <img src="https://img.shields.io/badge/python-3.11-blue" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="license">
  <img src="https://img.shields.io/badge/LLM-Qwen2.5:7b-orange" alt="llm">
</p>

---

## 目录

- [项目演进](#项目演进)
  - [v0.1 · 打地基](#v01--打地基)
  - [v0.2 · 架构升级](#v02--架构升级)
  - [v0.3 · 规划中](#v03--规划中)
- [项目结构](#项目结构)
- [快速启动](#快速启动)
- [核心设计](#核心设计)
- [API 接口](#api-接口)
- [测试](#测试)
- [技术栈](#技术栈)

---

## 项目演进

> 这个项目不是一开始就设计成现在的样子。
> 它从最简单的"if-else 路由"开始，在一次又一次遇到问题后，
> 学习新的架构模式，重构，测试，再发现问题，再重构。
> 下面是这个迭代过程。

---

### v0.1 · 打地基

`FastAPI` `SQLite` `LangGraph` `Ollama`

**目标：** 让一个跑在本地的 LLM 能存记忆、能查知识库、能聊天。

<p align="center">
  <img src="https://mermaid.ink/img/pako:eNp1kMEKwjAMQP-l5KzivoOdBNHDQPDgQfBQa9DgtRtpKyjSf7eqIOLMJYT3SF46sJ4UshyXik-OBUFLRtMblKbgtHg4sOR9u8k03lAzlwsoJTu3pFNJj8nB5RTF0hAvDQKicJ2ah3aK8_6gj3JRjLp0jwPJa20mCj0_9ksH0rwI4s_JD6D84BnErO_BrSOhYd3q1jK2LPkBn4PYXg" alt="v0.1 architecture">
</p>

最初的思路很直觉 —— 用户消息来了，先猜他想干什么，再路由到对应模块：

```
用户输入  →  detect_intent（规则匹配 + LLM 兜底）
                ├─ "记住xxx"    →  写 SQLite
                ├─ "搜索xxx"    →  查 ChromaDB
                └─ 其他         →  LLM 聊天
```

**这版能用，但跑了一段时间后，5 个架构问题逐渐暴露：**

<table>
<tr>
  <td width="30"><strong>1</strong></td>
  <td><strong>意图检测不可靠</strong></td>
</tr>
<tr><td></td><td>
LLM 被要求输出一个字符串标签（<code>"chat"</code> / <code>"remember"</code> / <code>"search"</code>），再用 if-else 路由。Qwen2.5:7b 经常返回 <code>"chat "</code>（多余空格）或 <code>"我要聊天"</code>（整句中文），case 匹配直接失效。
</td></tr>

<tr>
  <td width="30"><strong>2</strong></td>
  <td><strong>两条聊天管线各自实现</strong></td>
</tr>
<tr><td></td><td>
<code>/chat</code>（JSON）和 <code>/chat/stream</code>（SSE）是两套独立代码，各自构建输入、各自调 agent、各自处理错误。修一个 bug 要改两处，两边 SSE 格式还不统一。
</td></tr>

<tr>
  <td width="30"><strong>3</strong></td>
  <td><strong>不支持删除记忆</strong></td>
</tr>
<tr><td></td><td>
用户只能存不能删。AgentState 字段在三个文件中各自定义一套，互相对不上。
</td></tr>

<tr>
  <td width="30"><strong>4</strong></td>
  <td><strong>模型名硬编码</strong></td>
</tr>
<tr><td></td><td>
<code>agent/graph.py</code> 里 <code>"qwen2.5:7b"</code> 写死在代码里。换模型要改源码，不是改配置。
</td></tr>

<tr>
  <td width="30"><strong>5</strong></td>
  <td><strong>错误无降级</strong></td>
</tr>
<tr><td></td><td>
Ollama 挂了 → agent 直接崩溃 → HTTP 500。前端不知道发生了什么。
</td></tr>
</table>

> **关键认知：** 这些问题在 Demo 里都不是问题。但当系统需要处理"先查 Redis 文档，然后记住它的核心配置"这种多意图请求、需要被前端消费、需要稳定运行时，就成了真正的架构债。

---

### v0.2 · 架构升级

`ReAct 循环` `@tool 工具调用` `统一管线` `SSE 协议`

**核心洞察：**

<p align="center">
  <strong>不要让代码猜 LLM 想干什么。<br>让 LLM 直接告诉代码要调用哪个函数。</strong>
</p>

在研究 LangGraph 文档后，找到了两个关键能力：

<blockquote>
<p><strong><code>@tool</code> + <code>bind_tools()</code></strong></p>
<p>把 Python 函数包装成 LLM 可调用的工具。LLM 不再输出模糊的字符串，而是输出结构化的 <code>tool_calls</code>：</p>
<pre><code>{"name": "search_knowledge", "args": {"query": "Redis 配置"}}</code></pre>
<p>代码只负责执行，不用解析。</p>
</blockquote>

<blockquote>
<p><strong><code>create_react_agent</code></strong></p>
<p>LangGraph 预构建的 ReAct（Reasoning + Acting）循环。LLM 在循环中自主决策：</p>
<pre><code>需要调工具吗？→ 调哪个？→ 结果够吗？→ 还需要更多信息吗？→ 重复直到完成</code></pre>
</blockquote>

**新架构：**

```
用户输入
  │
  ▼
ChatService.stream_events()        ◀── 唯一业务入口，/chat 和 /chat/stream 共用
  │
  ▼
┌─────────────────────────────┐
│     create_react_agent       │
│                              │
│   agent 节点 ──有 tool_calls──▶ tools 节点
│       ▲                          │
│       └────── 工具结果 ──────────┘
│                              │
│   无 tool_calls → 输出最终回答  │
└─────────────────────────────┘
  │
  ▼
SSE 事件流 → 前端消费
```

**v0.1 vs v0.2：每个问题是怎么解决的**

| 问题 | v0.1 | v0.2 |
|------|:-----|:-----|
| 意图检测 | LLM 输出字符串 → if-else 路由 | `@tool` + `bind_tools()` → 结构化 `tool_calls` |
| 双管线 | 两套独立代码路径 | `ChatService.stream_events()` 统一入口 |
| 增删改查 | 只能存、查 | `save` / `list` / `delete` / `delete_all` 完整 CRUD |
| 模型切换 | 源码硬编码 | `settings.ollama_chat_model` 从 `.env` 读 |
| State 管理 | 三个文件各自定义 | 统一 `GraphState(TypedDict)` |
| 错误处理 | 崩溃 → 500 | try/except → `error` SSE 事件 |
| 编码兼容 | Windows 乱码 | UTF-8 with BOM |
| ChromaDB 兼容 | 1.5.9+ API 不匹配 | `NotFoundError` + 自定义 Embedding |

**工程化成果：**
- **157 个测试**（136 单元 · 6 集成 · 7 E2E · 3 性能 · 5 安全）
- **SSE 事件协议**文档化：`meta` → `stage` → `final` → `done`
- **LangGraph astream_events v2** 事件映射到自定义 SSE 格式

---

### v0.3 · 规划中

`Reflexion 循环` `多 Agent 审核` `被动记忆提取`

当前 ReAct 的局限：Agent 生成回答后不会自我审查。引用不存在的文档、代码有 bug、格式不对 —— Agent 都发现不了。

**方案：** 引入 Reflexion 模式 —— Agent 生成 → 审核员指出不足 → Agent 修正 → 循环直到通过或达到上限。同时规划被动记忆提取：不等用户说"记住"，而是定期分析对话历史自动发现潜在偏好。

---

## 项目结构

```
private-agent/
├── app/                 FastAPI 入口 · ChatService 统一管线
├── agent/               LangGraph ReAct 循环 · @tool 工具定义
├── tools/               知识库检索工具
├── llm/                 Ollama HTTP 客户端
├── memory/              SQLite 存储（WAL 模式）
├── rag/                 ChromaDB 向量库 · 文档切块 · 本地导入
├── config/              Pydantic Settings
├── knowledge/           本地 Markdown 笔记
├── tests/               157 个测试
├── static/              前端 SPA + SSE 客户端
└── pictures/            架构图
```

---

## 快速启动

```bash
# 1. 拉取模型
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 2. 安装依赖
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

# 3. 导入知识库
curl -X POST http://127.0.0.1:8000/ingest/local \
  -H "Content-Type: application/json" \
  -d '{"directory": "knowledge"}'

# 4. 启动
uvicorn app.main:app --reload
# 浏览器打开 http://127.0.0.1:8000
```

---

## 核心设计

### ReAct 推理循环

```
create_react_agent(model=ChatOllama, tools=TOOLS, state_schema=AgentState)
                              │
                              ▼
              ┌───────────────────────────┐
              │       agent 节点           │
              │  LLM 分析输入 + 对话历史    │
              │  决定：直接回答 or 调工具   │
              └──────────┬────────────────┘
                         │
              有 tool_calls │ 无 tool_calls
                         │      │
              ┌──────────▼──┐   │
              │  tools 节点  │   │
              │  执行工具调用 │   │
              │  结果回传     │   │
              └──────┬───────┘   │
                     │           │
                     └─────循环──┘
                                │
                                ▼
                          最终回答
```

### 5 个 LLM 可调用工具

| 工具 | 参数 | 底层 |
|------|------|------|
| `search_knowledge` | `query: str` | ChromaDB Top-5 语义检索 |
| `save_memory` | `key, value, category` | SQLite INSERT OR REPLACE |
| `list_memories` | `category?` | SQLite SELECT + 分类筛选 |
| `delete_memory` | `key` | SQLite DELETE |
| `delete_all_memories` | — | 遍历删除（需确认） |

### 统一 SSE 事件流

`ChatService.stream_events()` 是 `/chat` 和 `/chat/stream` 的唯一入口，产出标准事件流：

```
meta  {"request_id":"...", "thread_id":"..."}
stage {"stage":"正在检索知识库...", "message":"查找相关文档"}
final {"content":"根据你的知识库...", "citations":[]}
done  {"request_id":"..."}
```

- `/chat` → 遍历流，收集 `final` → 返回 JSON
- `/chat/stream` → 逐条包装为 `data: {json}\n\n` → SSE 推送

### 文档切块

```
Markdown 文件
  → 按 ## 标题分割
    → 超长段落按空行分割
      → 超长段落按 300 字窗口（50 字重叠）切割
```

---

## API 接口

### 聊天
| `POST` | `/chat` | 同步，返回 JSON |
| `POST` | `/chat/stream` | 流式，SSE 事件流 |

### 记忆
| `POST` | `/memory/remember` | `{key, value, category}` |
| `GET` | `/memory/list` | `?category=tech_stack` |
| `DELETE` | `/memory/delete/{key}` | — |
| `DELETE` | `/memory/delete-all` | — |

### 知识库
| `POST` | `/knowledge/search` | `{query, top_k}` |
| `POST` | `/ingest/local` | `{directory}` |

### 系统
| `GET` | `/health` | Ollama 状态 + 模型列表 |
| `GET` | `/` | 前端对话界面 |

---

## 测试

```bash
pytest tests/ -v
```

| 类型 | 数量 | 覆盖 |
|:-----|:----:|:-----|
| 单元测试 | 136 | 工具 · 存储 · API · 切块 · 格式化 · Ollama |
| 集成测试 | 6 | Agent 全流程 · 多工具协作 |
| E2E | 7 | 对话流程 · 记忆 CRUD · 知识库搜索 |
| 性能 | 3 | 响应时间 · 并发 |
| 安全 | 5 | 空消息 · 超长输入 · 特殊字符 · 无效 ID |

---

## 技术栈

| 层 | 选型 | 为什么 |
|:---|:-----|:-------|
| 框架 | FastAPI | 原生异步 · 自动 OpenAPI |
| Agent | LangChain + LangGraph | ReAct 预构建 · `bind_tools` |
| LLM | Ollama · Qwen2.5:7b | 本地运行 · 零成本 |
| Embedding | Ollama · nomic-embed-text | 768 维本地向量化 |
| 向量库 | ChromaDB | 持久化 · 余弦检索 |
| 业务库 | SQLite (WAL) | 零配置 · 适合单机 |
| 测试 | pytest + asyncio | 异步支持 · fixture 复用 |

---

<p align="center">
  <sub>MIT License · <a href="https://github.com/zzj024/private-agent">GitHub</a></sub>
</p>
