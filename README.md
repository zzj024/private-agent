# Private Agent

> 私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。
> Claude Code 是执行手；Private Agent 是知识管家。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange)
![Chroma](https://img.shields.io/badge/ChromaDB-0.6-purple)
![SQLite](https://img.shields.io/badge/SQLite-WAL-lightgrey)
![Ollama](https://img.shields.io/badge/Ollama-qwen2.5%3A7b-yellow)
![Tests](https://img.shields.io/badge/tests-103_passed-brightgreen)

---

## 项目定位

| 职责归属 | Claude Code | Private Agent |
|---------|------------|---------------|
| 写代码、改 bug、重构 | ✅ | ❌ |
| 跑测试、执行命令 | ✅ | ❌ |
| 读当前项目代码 | ✅ | ❌ |
| 长期学习资料保存 | ❌ | ✅ |
| 个人知识库管理 | ❌ | ✅ |
| 记忆技术栈/薄弱点/目标 | ❌ | ✅ |
| AI 文档更新监控 | ❌ | ✅ |
| 后续 MCP 暴露给 Claude Code | ❌ | ✅ |

---

## 功能

- **💬 聊天** — 通过 LangGraph 工作流与 Agent 对话，自动检索知识库和长期记忆
- **🧠 长期记忆** — 保存技术栈、偏好、目标、薄弱点等信息
- **📚 知识库** — RAG 检索增强生成，基于 Chroma 向量数据库
- **📥 本地笔记导入** — 导入 `.md`/`.txt` 文件，自动切块和向量化

---

## 快速启动

### 前置条件

- Python 3.11+
- [Ollama](https://ollama.com/)（已安装 `qwen2.5:7b` 和 `nomic-embed-text` 模型）

### 安装

```bash
git clone <your-repo-url>
cd private-agent

python -m venv venv
source venv/Scripts/activate  # Windows Git Bash
pip install -r requirements.txt

# 拉取 Ollama 模型（如尚未拉取）
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### 启动

```bash
uvicorn app.main:app --reload
```

打开浏览器访问 `http://127.0.0.1:8000/`

### 测试

```bash
python -m pytest tests/ -v
```

---

## 项目结构

```
private-agent/
├── app/main.py           # FastAPI 入口 + 路由
├── app/web.py            # 前端页面
├── agent/
│   ├── graph.py          # LangGraph 工作流（意图路由）
│   ├── state.py          # 状态定义
│   └── prompts.py        # 系统提示词
├── llm/ollama_client.py  # Ollama API 封装
├── memory/
│   ├── sqlite_store.py   # SQLite 存储封装
│   └── schema.sql        # 数据库表结构
├── rag/
│   ├── chroma_store.py   # Chroma 向量库封装
│   ├── chunker.py        # 文档切块
│   └── ingest_local.py   # 本地笔记导入
├── tools/knowledge_tools.py  # 知识库检索工具
├── config/settings.py    # 全局配置
└── tests/                # 测试（82 个）
```

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | FastAPI |
| 工作流引擎 | LangGraph |
| 本地 LLM | Ollama (qwen2.5:7b) |
| 向量库 | ChromaDB + nomic-embed-text |
| 关系库 | SQLite |
| 前端 | 纯 HTML + JavaScript + marked |
| 测试 | pytest |

---

## 版本规划

| 版本 | 功能 | 状态 |
|------|------|:----:|
| v0.1 | FastAPI 基础 + SQLite 记忆 + LangGraph 意图路由 + Ollama 聊天 | ✅ 完成 |
| v0.2 | Chroma RAG + 本地笔记导入 + 知识库检索 + ChatService 统一管线 | ✅ 完成 |
| v0.2-opt | Tool calling + ReAct 循环替代 detect_intent，混合意图支持，对话持久化 | 🔧 进行中 |
| v0.3 | 检索控制器 + DeepSeek 质量评估 + 前端框架 | 📋 规划 |
| v0.4 | MCP Server 暴露给 Claude Code | 📋 规划 |
| v0.5 | Docker + Tailscale | 📋 规划 |

---
---

## 架构迭代记录

记录每次架构决策的背景、权衡和调整，帮助后续开发者理解为什么这么做。

### v0.1 — 初始架构

目标：跑通完整的 聊天-记忆-知识库 链路。

架构：FastAPI + LangGraph + Ollama + SQLite + ChromaDB

关键模块：
- detect_intent 节点：正则规则匹配意图 + LLM 兜底解析 JSON
- 4 种意图：chat / remember / forget / list
- 条件路由走向对应执行节点

问题：
- Intent 只有 4 种，信息量有限
- 规则匹配死板，隐式记忆需求匹配不到
- JSON 解析不稳定，失败时静默降级
- 批量操作只能处理第一条
- 流式输出没有统一协议

### v0.2 — 统一管线 + 事件流（Phase 1 完成）

目标：统一 /chat 和 /chat/stream 业务逻辑，事件协议化。

变更：
1. 创建 ChatService — 共享业务管线，两种输出方式
2. SSE 事件协议 — 6 种事件类型
3. 规范性错误处理 — 全局 try/except
4. LangGraph astream() 支持流式事件

测试：103 个测试全部通过。

### v0.2-opt — 工具调用 + ReAct 循环（Phase 2 进行中）

目标：用工具调用替代 detect_intent，支持混合意图和批量操作。

变更：
1. @tool 装饰器定义 5 个工具
2. bind_tools() — Qwen 自判断调用工具
3. ReAct 循环节点 — 复杂问题分解为 task 列表循环执行
4. 规则兜底保留 — tool calling 失败时回退正则匹配

关键决策记录（2026-06-27）：
- 用 Qwen 拆 Task + ReAct 循环替代 DeepSeek 拆子问题 + 逐个执行
- 理由：Token 消耗更低、上下文可复用、数据库调用可合并
- 详细讨论见 ARCHITECTURE-v0.2.md 第 17 章

---

### 规划中

| 版本 | 焦点 |
|------|------|
| v0.3 | DeepSeek 质量评估 + 前端框架 + 监控 |
| v0.4 | MCP Server 暴露 |
| v0.5 | Docker + Tailscale 部署 |

## License

MIT
