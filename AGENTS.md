# private-agent

私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。

## 快速启动

```bash
cd C:\Users\Administrator\Desktop\项目\private-agent
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 教学约定

本项目默认启用 **teaching** 教学模式。
我是你的教学型结对编程助手（Tech Lead + Mentor），不是代码生成器。

进入项目后我将：
1. 自动检测技术栈和项目阶段
2. 分步讲解，确保你理解再动手
3. 代码以终端块输出（除非你明确授权我写文件）
4. 每段代码附讲解：做什么 + 为什么 + 面试怎么讲
5. 主动对比你已知的语言概念（Java 等）

## 项目结构

```
private-agent/
├── app/          FastAPI 入口和网页路由
├── agent/        LangGraph 工作流（ReAct + Reflexion）
├── llm/          LLM 客户端（Ollama 本地 / DeepSeek API）
├── memory/       SQLite 存储
├── rag/          Chroma 向量库 + 文档导入
├── tools/        工具函数
├── config/       配置
├── knowledge/    本地笔记来源
├── data/         数据存储
├── tests/        258 个测试
├── static/       前端文件
└── pictures/     架构图
```

## 当前阶段

### v0.2（已完成）
- ReAct 循环实现
- 工具调用替代意图识别
- 统一聊天管线
- 完整测试套件

### v0.3（已实现）
- Reflexion 循环（带缓存 + 结构化反馈 + 智能终止）
- 工具层数据缓存（contextvars 传递 state）
- DeepSeek 审核员检查
- 接口精简（3 个方法 -> 1 个）
- 100 个新测试（ReflexionState、审核模块、DeepSeek 客户端、工具缓存、集成、安全）

## 核心功能

### 1. ReAct 循环（v0.2）
- 动态工具调用：LLM 自动决定调用哪些工具
- 多意图处理：一次请求处理多个操作
- 自评完成度：LLM 自己判断任务是否完成

### 2. Reflexion 循环（v0.3 新增）
- 缓存下沉到工具层：缓存原始数据（ChromaDB 结果），不缓存 LLM 答案
- 结构化反馈：issues 和 suggestions 一一对应，便于逐条修正
- 智能终止：连续两次分数没提升 -> 提前终止
- 降级兜底：Reflexion 失败自动降级为普通 ReAct

### 3. 工具系统
- `search_knowledge`: 搜索私有知识库（带缓存）
- `save_memory`: 保存长期记忆
- `list_memories`: 列出记忆（带缓存）
- `delete_memory`: 删除记忆
- `delete_all_memories`: 删除所有记忆

### 4. 统一聊天管线
- `/chat`: 同步聊天（返回 JSON）
- `/chat/stream`: 流式聊天（SSE）
- 共享同一个 ChatService 业务逻辑

## 测试

### 运行所有测试
```bash
pytest tests/ -v
```

### 测试类型
- v0.1-v0.2 测试: 108 个（工具、存储、API、切块、格式化、Ollama、Agent 管线、E2E）
- v0.3 新增: 100 个（ReflexionState、审核模块、DeepSeek 客户端、工具缓存、集成、安全）

**总计：258 个测试**

## 相关文档

- [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md) — 系统架构与实施规划
- [TECH_DEBT.md](TECH_DEBT.md) — 技术债务跟踪
- [README.md](README.md) — 项目说明

## 开发指南

### 添加新工具
1. 在 `agent/tools.py` 中定义工具函数
2. 使用 `@tool` 装饰器
3. 添加到 `TOOLS` 列表
4. 编写单元测试

### 添加新 API 端点
1. 在 `app/main.py` 中定义路由
2. 创建请求/响应模型
3. 编写端到端测试

## 技术栈

- **后端**: Python 3.11 + FastAPI
- **AI 框架**: LangChain + LangGraph
- **LLM**: Ollama (Qwen2.5:7b) + DeepSeek API
- **向量数据库**: ChromaDB
- **关系数据库**: SQLite
- **测试框架**: pytest

## 配置

### 环境变量 (.env)
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
CHROMA_PATH=data/chroma
SQLITE_PATH=data/agent.db
```
