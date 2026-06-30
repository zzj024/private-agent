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
├── app/          # FastAPI 入口和网页路由
├── agent/        # LangGraph 工作流（ReAct 循环 + Reflexion 循环）
├── llm/          # LLM 路由（Ollama 本地 / API）
├── memory/       # SQLite 存储
├── rag/          # Chroma 向量库 + 文档导入
├── tools/        # 工具函数
├── config/       # 配置
├── knowledge/    # 本地笔记来源
├── data/         # 数据存储
├── tests/        # 测试套件（120 个测试）
├── static/       # 前端文件
└── pictures/     # 架构图
```

## 当前阶段

### v0.2（已完成）
- ? ReAct 循环实现
- ? 工具调用替代意图识别
- ? 统一聊天管线
- ? 完整测试套件（120 个测试）
- ? 修复 chromadb 兼容性
- ? 修复编码问题

### v0.3（开发中）
- ?? Reflexion 循环（带缓存 + 结构化反馈 + 智能终止）
- ?? 缓存 key 标准化归一化
- ?? 结构化 issues 和 suggestions
- ?? 连续退化提前终止
- ?? 最低分数线兜底
- ?? 审核员检查

## 核心功能

### 1. ReAct 循环（v0.2）
- 动态工具调用：LLM 自动决定调用哪些工具
- 多意图处理：一次请求处理多个操作
- 自评完成度：LLM 自己判断任务是否完成

### 2. Reflexion 循环（v0.3 新增）
- **临时缓存列表**：循环外维护缓存，减少重复数据库查询
  - 缓存 key 标准化归一化（"Redis 配置" 和 "redis 配置" 命中同一缓存）
  - 缓存在单次请求内有效，跨请求不共享
- **结构化反馈**：issues 和 suggestions 结构化，便于逐条修正
- **智能终止**：连续两次分数没有提升 → 提前终止
- **最低分数线**：score < 4 返回 None，前端显示"暂时无法回答"
- **审核员检查**：独立 LLM 评估答案质量

### 3. 工具系统
- `search_knowledge`: 搜索私有知识库
- `save_memory`: 保存长期记忆
- `list_memories`: 列出记忆
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
- **单元测试**: 99 个
- **集成测试**: 6 个
- **端到端测试**: 7 个
- **性能测试**: 3 个
- **安全测试**: 5 个

**总计：120 个测试，全部通过！**

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

- **后端**: Python 3.13 + FastAPI
- **AI 框架**: LangChain + LangGraph
- **LLM**: Ollama (Qwen2.5:7b)
- **向量数据库**: ChromaDB
- **关系数据库**: SQLite
- **测试框架**: pytest

## 配置

### 环境变量 (.env)
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
CHROMA_PATH=data/chroma
SQLITE_PATH=data/private_agent.db
```

## 更新日志

### v0.3 (2026-06-30) - 开发中
- ?? 实现 Reflexion 循环（带缓存 + 结构化反馈 + 智能终止）
- ?? 缓存 key 标准化归一化
- ?? 结构化 issues 和 suggestions
- ?? 连续退化提前终止
- ?? 最低分数线兜底
- ?? 审核员检查

### v0.2 (2026-06-30)
- ? 实现 ReAct 循环
- ? 工具调用替代意图识别
- ? 统一聊天管线
- ? 完整测试套件（120 个测试）
- ? 修复 chromadb 兼容性
- ? 修复编码问题

### v0.1 (2026-06-25)
- ? FastAPI 基础框架
- ? SQLite 存储
- ? LangGraph 工作流
- ? Ollama 集成
- ? 基础聊天功能
