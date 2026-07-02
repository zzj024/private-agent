# Private Agent

本地 LLM 驱动的私人知识管家 —— 从零构建的 AI Agent，具备长期记忆、私有知识库检索、ReAct 推理循环能力。

---

## 版本：v0.5（当前）

**状态：** 功能完整，所有 Bug 已修复。367 个测试通过。

### v0.4 → v0.5 新功能

| 功能 | 说明 |
|---|---|
| 前端重构 | 双核工作台（Chat/Review/Library/Knowledge/Settings），卡片流设计 |
| 被动记忆提取 | LLM 自动从对话提取候选，自动分级，冲突检测 |
| 记忆注入 | 聊天自动引用已确认记忆 |
| 聊天历史 | 多轮对话上下文自动加载 |
| 统一 LLM 配置 | 支持 Ollama/DeepSeek/Moonshot，前端设置页一键切换 |
| 知识库增强 | 系统文件选择、独立进度条、分页浏览、搜索分页+编辑 |
| Bug 修复 | 编辑消失、重复 Toast、无关搜索、搜索无分页等 6 个 Bug |

详见 [CLAUDE.md](CLAUDE.md) 和 [docs/V0.5_DESIGN.md](docs/V0.5_DESIGN.md)

### 项目演进

- v0.1: 打地基（FastAPI + LangGraph + SQLite + ChromaDB）
- v0.2: 架构升级（@tool + bind_tools + create_react_agent）
- v0.3: 智能检索 A++ + 对话管理 + Reflexion 循环
- v0.4: 前端重构 + 历史记忆
- v0.5: 被动记忆提取 + 自动分级 + 统一模型配置 + 知识库管理

---

## 项目结构

```
private-agent/
├── app/          FastAPI 入口 · ChatService 统一管线
├── agent/        ReAct 循环 · Reflexion 循环 · @tool 工具定义
├── tools/        知识库检索 · LLM 重排序
├── llm/          统一 LLM 工厂 · Ollama/DeepSeek 客户端
├── memory/       SQLite 存储 · 被动提取 · 冲突检测
├── rag/          ChromaDB 向量库 · 文档切块 · 本地导入
├── config/       Pydantic Settings
├── knowledge/    本地 Markdown 笔记
├── tests/        367 个测试
├── docs/         设计文档 · Bug 记录
└── static/       前端单文件 SPA (index.html, ~1600行)
```

---

## 快速启动

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

python -m venv venv
source venv/Scripts/activate   # Windows
pip install -r requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
# 浏览器打开 http://127.0.0.1:8000
```

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 同步聊天 |
| POST | `/chat/stream` | SSE 流式聊天 |
| POST | `/memory/remember` | 保存记忆（冲突检测） |
| GET | `/memory/list` | 查看记忆 |
| DELETE | `/memory/delete/{key}` | 删除指定记忆 |
| DELETE | `/memory/delete-all` | 删除全部记忆 |
| GET | `/memory/candidates` | 列出候选记忆 |
| POST | `/memory/candidates/{id}/accept` | 接受候选 |
| POST | `/memory/candidates/{id}/reject` | 拒绝候选 |
| POST | `/knowledge/search` | 搜索知识库（文本） |
| POST | `/knowledge/search/chunks` | 搜索知识库（结构化分页） |
| POST | `/knowledge/upload` | 上传文件（异步） |
| GET | `/knowledge/progress/{id}` | 查询导入进度 |
| GET | `/knowledge/stats` | 知识库统计 |
| GET | `/knowledge/chunks/{file}` | 分页浏览文本块 |
| PUT | `/knowledge/chunk/{id}` | 编辑文本块 |
| DELETE | `/knowledge/chunk/{id}` | 删除文本块 |
| DELETE | `/knowledge/chunks/{file}` | 删除文件 |
| DELETE | `/knowledge/collection` | 清空知识库 |
| GET | `/settings/llm` | 获取 LLM 配置 |
| PUT | `/settings/llm` | 更新 LLM 配置 |
| POST | `/settings/llm/test` | 测试 LLM 连接 |
| GET | `/conversations` | 会话列表 |
| POST | `/conversations` | 创建会话 |
| GET | `/conversations/{id}` | 会话详情 |
| POST | `/conversations/{id}/messages` | 保存消息 |
| PUT | `/conversations/{id}/rename` | 重命名 |
| DELETE | `/conversations/{id}` | 删除会话 |

---

## 技术栈

| 层 | 选型 | 说明 |
|:---|:-----|:-----|
| 框架 | FastAPI | 原生异步 |
| Agent | LangChain + LangGraph | ReAct + Reflexion |
| LLM | Ollama / DeepSeek / Moonshot | 统一可切换 |
| Embedding | Ollama nomic-embed-text | 768 维 |
| 向量库 | ChromaDB | 持久化 |
| 存储 | SQLite (WAL) | 零配置 |

---

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 项目指南（最全）
- [docs/BUGS.md](docs/BUGS.md) — Bug 记录
- [docs/V0.5_DESIGN.md](docs/V0.5_DESIGN.md) — v0.5 设计文档
- [docs/SMART_SEARCH_DESIGN.md](docs/SMART_SEARCH_DESIGN.md) — 智能检索方案
- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) — 架构详解
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务
