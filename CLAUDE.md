# CLAUDE.md

本文件为 Claude Code 在此项目中工作时提供指导。

## 项目概述

Private Agent 是一个私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。

## 当前状态

**版本：** v0.5
**状态：** 所有 Bug 已修复，功能完整
**测试：** 367 个测试（1 个预存在编码问题）

## v0.5 新增功能

### 前端重构
- 双核工作台布局：侧边栏 + 主视图（Chat / Review / Library / Knowledge / Settings）
- Notion + Linear 风格视觉系统，Toast 通知
- 记忆审核卡片流：置信度进度条、证据展开、行内编辑、批量操作
- 知识库：文件上传（系统原生弹窗多选）、每个文件独立进度条、双击分页浏览、搜索分页+编辑

### 被动记忆提取
- LLM 分析对话自动提取候选（改用统一 LLM 工厂，支持 Ollama/DeepSeek/Moonshot）
- v0.5 自动分级：高可信(≥0.85) 直接存入、中信(0.6-0.85) 人工审核、低信(<0.6) 自动丢弃
- 冲突检测：key 重复且值不同时强制送审，不覆盖旧值
- 延迟从 120s 改为 20s

### 记忆注入
- 聊天时自动将已确认记忆注入 LLM 上下文
- 对话历史自动加载（多轮上下文）

### 统一 LLM 配置
- 前端设置页面：预设卡片（Ollama/DeepSeek/Moonshot）+ 自定义新增 + 测试连接
- `llm/factory.py` 统一工厂：全局所有 LLM 调用共用同一配置
- 保存立即生效，无需重启

### 聊天历史修复
- ChatService 加载历史消息传入 LLM，解决"聊完就忘"问题
- Reflexion 审核保持用 DeepSeek 专用客户端（避免编码问题）

### Bug 修复
- BUG-001: LLM 不按格式返回 JSON → 格式适配器 + 重写 prompt
- BUG-002: 编辑文本块消失 → ChromaDB 改用 col.update()
- BUG-003: 导入完成 Toast 重复弹出 → 加 notified 标记
- BUG-005: 无关词搜索返回结果 → 删除兜底逻辑
- BUG-006: 搜索结果无分页 → 新增结构化搜索 API + 弹窗分页
- BUG-004: 编辑保存慢 → 乐观更新 UI

## 核心架构

### 文件组织
- `agent/`: LangGraph 工作流、ReAct 循环、Reflexion 循环、工具定义
- `app/`: FastAPI 路由和服务
- `tools/`: 知识库检索工具
- `llm/`: 统一 LLM 工厂 + Ollama/DeepSeek 客户端
- `memory/`: SQLite 存储 + 被动提取
- `rag/`: ChromaDB 向量存储 + 文档导入
- `config/`: 全局配置
- `knowledge/`: 本地笔记来源
- `tests/`: 367 个测试
- `static/`: 前端静态文件（单文件 index.html, ~1600 行）

### 命名约定
- 文件名：snake_case
- 类名：PascalCase
- 函数名：snake_case
- 常量：UPPER_SNAKE_CASE

## 常用命令

### 运行应用
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### 运行测试
```bash
pytest tests/ -v
```

### 注意事项
- chromadb 需在 get_collection 后手动设置 _embedding_function
- ChromaDB PersistentClient 单 worker 使用，多 worker 需改 server 模式
- Windows 终端编码问题：优先使用英文测试
- 被动记忆提取依赖 threading.Timer，uvicorn reload 时注意
- get_chroma_store() 使用 @lru_cache 单例模式

## 相关文档

- [README.md](README.md) — 项目说明
- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务
- [docs/BUGS.md](docs/BUGS.md) — Bug 记录
- [docs/V0.5_DESIGN.md](docs/V0.5_DESIGN.md) — v0.5 设计文档
- [docs/SMART_SEARCH_DESIGN.md](docs/SMART_SEARCH_DESIGN.md) — 智能检索方案
