# Private Agent

> 私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。
> Claude Code 是执行手；Private Agent 是知识管家。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange)
![Chroma](https://img.shields.io/badge/ChromaDB-0.6-purple)
![SQLite](https://img.shields.io/badge/SQLite-WAL-lightgrey)
![Ollama](https://img.shields.io/badge/Ollama-qwen2.5%3A7b-yellow)
![Tests](https://img.shields.io/badge/tests-82_passed-brightgreen)

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

| 版本 | 功能 |
|------|------|
| v0.1 | FastAPI 基础 + SQLite 记忆 + LangGraph 意图路由 + Ollama 聊天 |
| v0.2 | Chroma RAG + 本地笔记导入 + 知识库检索 |
| v0.3 | 网页导入 + 更新监控 + 流式响应 |
| v0.4 | MCP Server 暴露给 Claude Code |
| v0.5 | Docker + Tailscale |

---

## License

MIT
