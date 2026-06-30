# CLAUDE.md

本文件为 Claude Code 在此项目中工作时提供指导。

## 项目概述

Private Agent 是一个私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。

## 当前状态

**版本：** v0.2（已完成）
**状态：** 所有测试通过（120 个测试）

## 核心架构

### ReAct 循环
- 使用 LangGraph 的 create_react_agent
- LLM 通过 bind_tools() 动态调用工具
- 支持多意图处理和循环执行

### 工具系统
- search_knowledge: 搜索私有知识库
- save_memory: 保存长期记忆
- list_memories: 列出记忆
- delete_memory: 删除记忆
- delete_all_memories: 删除所有记忆

### 统一聊天管线
- ChatService 统一处理 /chat 和 /chat/stream
- 使用 AsyncGenerator 实现事件流
- 支持 SSE 流式输出

## 代码规范

### 文件组织
- `agent/`: LangGraph 工作流和工具定义
- `app/`: FastAPI 路由和服务
- `memory/`: SQLite 存储
- `rag/`: ChromaDB 向量存储
- `tests/`: 测试文件

### 命名约定
- 文件名：snake_case
- 类名：PascalCase
- 函数名：snake_case
- 常量：UPPER_SNAKE_CASE

### 测试规范
- 单元测试：test_*.py
- 集成测试：test_integration.py
- 端到端测试：test_e2e.py
- 性能测试：test_performance.py
- 安全测试：test_security.py

## 常用命令

### 运行应用
```bash
uvicorn app.main:app --reload
```

### 运行测试
```bash
pytest tests/ -v
```

### 运行特定测试
```bash
pytest tests/test_tools.py -v
```

## 注意事项

### 编码问题
- Windows 环境下使用 UTF-8 编码
- 测试文件中避免使用中文注释和字符串
- 使用英文替代中文

### chromadb 兼容性
- chromadb 1.5.9+ 需要 embed_query 方法
- 使用 NotFoundError 替代 InvalidCollectionException
- SimpleEmbedding 需要实现 embed_query

### LangGraph 版本
- 使用 create_react_agent 构建 ReAct 循环
- 需要 remaining_steps 字段
- 使用 bind_tools() 绑定工具

## 相关文档

- [README.md](README.md) — 项目说明
- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) — 系统架构
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务
- [AGENTS.md](AGENTS.md) — 项目指南

## 更新日志

### v0.2 (2026-06-30)
- ? 实现 ReAct 循环
- ? 工具调用替代意图识别
- ? 统一聊天管线
- ? 完整测试套件（120 个测试）
- ? 修复 chromadb 兼容性
- ? 修复编码问题
