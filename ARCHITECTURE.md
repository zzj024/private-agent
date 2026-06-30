# private-agent v0.1 — 系统架构与实施规划

> **⚠️ 历史文档：** 本文档是 v0.1 阶段的原始架构规划。实际实施过程中发生了重大架构变更（如意图路由改为 ReAct 循环、文件组织调整等）。最新架构请参阅 **[ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md)**。

## 一、项目定位

> Claude Code 是执行手；private-agent 是知识管家。

| 职责归属 | Claude Code | private-agent |
|---------|------------|---------------|
| 写代码、改 bug、重构 | ✅ | ❌ |
| 跑测试、执行命令 | ✅ | ❌ |
| 读当前项目代码 | ✅ | ❌ |
| 长期学习资料保存 | ❌ | ✅ |
| 个人知识库管理 | ❌ | ✅ |
| 记忆技术栈/薄弱点/目标 | ❌ | ✅ |
| 整理面试题/踩坑记录 | ❌ | ✅ |
| AI 文档更新监控 | ❌ | ✅ |
| 后续 MCP 暴露给 Claude Code | ❌ | ✅ |

---

## 二、总体架构

```
┌─────────────────────────────────────────────┐
│              用户 (浏览器/CLI)                │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│          FastAPI Web 层 (app/)               │
│  /chat  /ingest  /memory  /knowledge /review │
└──────┬──────────────────────────────┬───────┘
       │                              │
┌──────▼──────────┐     ┌────────────▼──────────┐
│  Agent 工作流    │     │      工具层            │
│  (agent/)       │     │  (tools/)             │
│  LangGraph      │◄────│  知识检索/记忆读写     │
│  意图路由        │     │  文档导入/更新检测     │
└──────┬──────────┘     └────────────┬──────────┘
       │                             │
┌──────▼─────────────────────────────▼──────────┐
│              LLM 路由层 (llm/)                 │
│  本地: Ollama (qwen2.5:7b)                     │
│  远程: DeepSeek/Claude API (预留)              │
└──────┬──────────────────────────────┬─────────┘
       │                              │
┌──────▼──────────┐     ┌────────────▼──────────┐
│   SQLite 存储    │     │   Chroma 向量库        │
│  (memory/)      │     │  (rag/)               │
│  conversations  │     │  personal_knowledge    │
│  memories       │     │  doc_type 分类         │
│  doc_sources    │     │                       │
│  doc_updates    │     │                       │
└─────────────────┘     └───────────────────────┘
```

---

## 三、实施步骤（分 3 步迭代）

### Phase 1：项目骨架 + FastAPI + SQLite（P0）

**目标：** 能启动服务、能保存记忆、能简单聊天

| # | 文件 | 内容 |
|---|------|------|
| 1 | `requirements.txt` | 所有依赖 |
| 2 | `.env.example` | 环境变量模板 |
| 3 | `config/settings.py` | Pydantic Settings 配置 |
| 4 | `config/sources.yaml` | AI 文档来源配置 |
| 5 | `memory/schema.sql` | SQLite 建表语句 |
| 6 | `memory/sqlite_store.py` | SQLite 存取封装 |
| 7 | `llm/router.py` | LLM 路由（本地/API） |
| 8 | `llm/ollama_client.py` | Ollama 调用封装 |
| 9 | `llm/api_client.py` | API 调用占位 |
| 10 | `agent/state.py` | LangGraph 状态定义 |
| 11 | `agent/prompts.py` | 系统提示词 |
| 12 | `agent/graph.py` | LangGraph 主工作流 |
| 13 | `app/main.py` | FastAPI 入口 + 路由 |
| 14 | `app/web.py` | 极简网页路由 |

**Phase 1 验收标准：**
```bash
uvicorn app.main:app --reload
# 访问 http://127.0.0.1:8000/health → {"status": "ok"}
# POST /chat → 能对话
# POST /memory/remember → 能保存记忆
# GET /memory/list → 能看到记忆
```

> **实施备注：** 实际代码中 `config/sources.yaml`、`llm/router.py`、`llm/api_client.py` 未创建。LLM 路由策略被简化为直接使用 Ollama。

---

### Phase 2：Chroma + RAG + 本地导入（P0-P1）

**目标：** 能导入本地笔记、能搜索知识库

| # | 文件 | 内容 |
|---|------|------|
| 1 | `rag/chroma_store.py` | Chroma 向量库封装（CRUD） |
| 2 | `rag/chunker.py` | 文档切块策略 |
| 3 | `rag/ingest_local.py` | 本地 Markdown/txt 导入 |
| 4 | `rag/ingest_web.py` | 网页文档导入（占位） |
| 5 | `tools/knowledge_tools.py` | 知识检索工具函数 |
| 6 | `tools/memory_tools.py` | 记忆读写工具函数 |

**Phase 2 验收标准：**
```bash
POST /ingest/local → 导入 knowledge/ 下的笔记
POST /knowledge/search → 返回相关 chunk
/chat 中能结合知识库回答
```

> **实施备注：** 实际代码中 `rag/ingest_web.py` 未单独创建（网页导入为 app/main.py 中的占位端点），`tools/memory_tools.py` 未创建（记忆工具直接实现在 `agent/tools.py` 中）。

---

### Phase 3：Web 导入 + 更新检测 + Web UI（P1-P2）

**目标：** 能监控文档更新、有简单网页界面

| # | 文件 | 内容 |
|---|------|------|
| 1 | `rag/ingest_web.py` | 网页抓取+导入（完整实现） |
| 2 | `tools/update_tools.py` | 文档更新检测工具 |
| 3 | `app/web.py` | 完整极简前端 |
| 4 | 更新 `agent/graph.py` | 加入更新检测路由 |

**Phase 3 验收标准：**
```bash
POST /ingest/web → 能抓取导入网页
POST /updates/check → 能检测文档更新
GET /updates/recent → 能看到最近更新
POST /review/weekly → 能生成周复盘
浏览器打开能看到 4 个入口界面
```

> **实施备注：** Phase 3 部分提前实施：Web UI（static/index.html）已在 v0.2 构建，`/ingest/web`、`/updates/*`、`/review/weekly` 端点在 app/main.py 中作为占位 API 存在，等待后续完整实现。

---

## 四、核心模块设计

### 4.1 Agent 工作流（agent/graph.py）

> **⚠️ v0.2 已改为 ReAct 循环。** 以下流程图是 v0.1 原始设计（意图路由），
> v0.2 使用 `create_react_agent` + `bind_tools()` 替代意图判断，
> LLM 自动决定调用哪些工具。详见 [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md)。

```
用户输入
  │
  ▼
┌─────────────────────┐
│ 意图判断             │
│ (规则 + LLM 辅助)    │   ← v0.2 已移除，改为 ReAct 循环
└──────┬──────────────┘
       │
  ┌────┼────┬──────────┐
  ▼    ▼    ▼          ▼
记住  查询  普通聊天   更新
 │    │    │          │
 ▼    ▼    ▼          ▼
写   查   读记忆     查文档
SQLite Chroma + 查Chroma  源
 │    │    │          │
 └────┴────┴──────────┘
       │
       ▼
    生成回答
       │
       ▼
    保存会话
```

**原意图判断逻辑（v0.1，已废弃）：**
- 包含"记住"或"remember" → memory_write
- 包含"搜索"、"查"、"找"、"search"等 → knowledge_search
- 包含"更新"、"检查"、"check update" → check_updates
- 其他 → 普通聊天（结合上下文）

### 4.2 数据库设计（SQLite）

```sql
-- 会话表
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 消息表
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,          -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

-- 长期记忆表
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',  -- tech_stack, weak_point, goal, project, preference
    confidence REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 文档源表
CREATE TABLE document_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT DEFAULT 'docs',    -- docs, blog, github
    tags TEXT,                   -- JSON array
    last_hash TEXT,
    last_checked_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 文档更新记录表
CREATE TABLE document_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    url TEXT NOT NULL,
    old_hash TEXT,
    new_hash TEXT,
    summary TEXT,
    relevance TEXT,              -- high, medium, low
    created_at TEXT DEFAULT (datetime('now'))
);
```

> **备注：** 以上为 v0.1 原始设计。实际 `memory/schema.sql` 使用了 `datetime('now', 'localtime')`，`memories.category` 默认值为 `''`。`document_sources` 和 `document_updates` 表已创建但尚未在应用代码中使用。

### 4.3 Chroma Collection 设计

- **Collection 名称:** `personal_knowledge`
- **Embedding 模型:** Ollama 本地 (nomic-embed-text 或 mxbai-embed-large)

**Metadata 结构（实际实现）：**
```python
{
    "source": "文件名",
    "file_path": "完整路径",
    "topic": "父目录名",
    "header": "Markdown 标题"
}
```

> **备注：** v0.1 原始设计包含 `doc_type`、`tags`、时间戳等字段，实际实现中简化为上述结构。

### 4.4 LLM 路由策略

| 任务类型 | 模型 | 说明 |
|---------|------|------|
| 普通聊天 | Ollama 本地 (qwen2.5:7b) | 响应快、免费 |
| 工具调用/决策 | Ollama (Qwen2.5:7b bind_tools) | v0.2 使用 ReAct + tool calling |
| 文档总结 | Ollama 本地 | 轻度总结 |
| 复杂分析 | API (预留) | OpenAI/Claude |
| Embedding | Ollama (nomic-embed-text) | 本地生成 |

---

## 五、API 接口一览

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/health` | - | 健康检查 |
| POST | `/chat` | `{"message": "...", "conversation_id": null}` | 聊天 |
| POST | `/ingest/local` | `{"directory": "knowledge/ai-agent"}` | 导入本地笔记 |
| POST | `/ingest/web` | `{"url": "...", "topic": "..."}` | 导入网页文档 |
| POST | `/memory/remember` | `{"key": "...", "value": "...", "category": "..."}` | 保存记忆 |
| GET | `/memory/list` | `category=tech_stack` | 查看记忆 |
| POST | `/knowledge/search` | `{"query": "...", "top_k": 5}` | 搜索知识库 |
| POST | `/updates/check` | - | 检查文档更新 |
| GET | `/updates/recent` | `days=7` | 查看最近更新 |
| POST | `/review/weekly` | - | 生成本周复盘 |

---

## 六、安全边界

| 规则 | 说明 |
|------|------|
| 只读项目目录 | 不读取项目外的文件 |
| 不读 .env | 敏感配置不进入上下文 |
| 不读 ~/.ssh | 不碰 SSH 密钥 |
| 不自动上传 | 不上传私人代码 |
| 不执行 shell | 第一版无 shell_exec 工具 |
| API key 仅 .env | 不硬编码 |
| 仅本地监听 | `127.0.0.1` 不暴露公网 |

---

## 七、风险与缓解

| 风险 | 缓解 |
|------|------|
| Ollama 本地模型质量不够 | 预留 API 接口，可切换 |
| Chroma 在 Windows 下兼容 | 使用 Chroma 最新版，pip install chromadb |
| 中文 embedding 效果差 | 选支持中文的模型（bge-m3 等） |
| 网页抓取被反爬 | 加 User-Agent，尊重 robots.txt |
| 文件路径编码问题 | Windows 下统一用 pathlib |

---

## 八、后续版本规划

| 版本 | 新增功能 |
|------|---------|
| v0.1 | 基础知识库 + 记忆 + 文档监控（已实施） |
| v0.2 | ReAct 循环 + 工具调用 + 统一聊天管线（已完成，与原始计划不同） |
| v0.3 | Reflexion 循环 + 多 Agent 审核 + 自动提示词优化 |
| v0.4 | MCP Server 暴露给 Claude Code |
| v0.5 | Docker + Tailscale + 多设备 |

> **备注：** 原始 v0.2 计划为"代码目录读取 + 项目总结 + README 生成"，实际实施中优先级调整为 ReAct 循环。
