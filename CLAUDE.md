# CLAUDE.md

本文件为 Claude Code 在此项目中工作时提供指导。

## 项目概述

Private Agent 是一个私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。

## 当前状态

**版本：** v0.3（已实现）
**状态：** 258 个测试全部通过

## 核心架构

### ReAct 循环（v0.2）
- 使用 LangGraph 的 create_react_agent
- LLM 通过 bind_tools() 动态调用工具
- 支持多意图处理和循环执行

### Reflexion 循环（v0.3）
- Agent 生成 -> 审核员打分 -> 未通过则带反馈重试 -> 循环
- 工具层数据缓存：缓存原始数据（ChromaDB 结果），不缓存 LLM 答案
- contextvars 传递 ReflexionState 给工具函数
- 审核员通过 DeepSeek API 评估回答质量
- 失败自动降级为普通 ReAct

### 工具系统
- search_knowledge: 搜索私有知识库（带缓存）
- save_memory: 保存长期记忆
- list_memories: 列出记忆（带缓存）
- delete_memory: 删除记忆
- delete_all_memories: 删除所有记忆

### 统一聊天管线
- ChatService 统一处理 /chat 和 /chat/stream
- 使用 AsyncGenerator 实现事件流
- 支持 SSE 流式输出

## 代码规范

### 文件组织
- `agent/`: LangGraph 工作流、ReAct 循环、Reflexion 循环、工具定义
- `app/`: FastAPI 路由和服务
- `tools/`: 知识库检索工具
- `llm/`: Ollama 客户端、DeepSeek 客户端
- `memory/`: SQLite 存储
- `rag/`: ChromaDB 向量存储 + 文档导入
- `config/`: 全局配置
- `knowledge/`: 本地笔记来源
- `tests/`: 258 个测试
- `static/`: 前端静态文件

### 命名约定
- 文件名：snake_case
- 类名：PascalCase
- 函数名：snake_case
- 常量：UPPER_SNAKE_CASE

### 测试规范
- 单元测试：test_*.py
- 集成测试：test_integration.py, test_reflexion_integration.py
- 端到端测试：test_e2e.py
- 性能测试：test_performance.py
- 安全测试：test_security.py, test_reflexion_security.py

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
pytest tests/test_reflexion_state.py -v
```

## 注意事项

### 编码问题
- Windows 环境下使用 UTF-8 with BOM 编码
- 测试文件中避免使用中文注释和字符串
- 使用英文替代中文

### chromadb 兼容性
- chromadb 0.6.x 同时捕获 NotFoundError 和 InvalidCollectionException
- get_collection 获取已有 collection 时需替换 _embedding_function
- OllamaEmbed 类实现 __call__ 方法适配 Chroma 接口

### LangGraph 版本
- 使用 create_react_agent 构建 ReAct 循环
- 需要 remaining_steps 字段
- 使用 bind_tools() 绑定工具

### Reflexion 循环
- 缓存下沉到工具层：只缓存原始数据（ChromaDB 结果），不缓存 LLM 答案
- 通过 contextvars 传递 ReflexionState，避免修改所有函数签名
- reflexion_loop 失败后自动降级为 run_agent（普通 ReAct）
- DeepSeek API key 从 .env 读取，源码默认值为空字符串

## 相关文档

- [README.md](README.md) — 项目说明
- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) — 系统架构
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务
- [AGENTS.md](AGENTS.md) — 项目指南
