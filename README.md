# Private Agent

私人知识库管理员 + 长期记忆系统 + AI 文档更新监控助手。

## 项目状态

| 版本 | 功能 | 状态 |
|------|------|------|
| v0.1 | FastAPI 基础 + SQLite 存储 + LangGraph 工作流 + Ollama 集成 | ? 完成 |
| v0.2 | ReAct 循环 + 工具调用 + 统一聊天管线 + 完整测试套件 | ? 完成 |
| v0.3 | Reflexion 循环（带缓存 + 结构化反馈 + 智能终止） + 多 Agent 审核 | ?? 开发中 |
| v0.4 | MCP Server 暴露给 Claude Code | ?? 计划中 |
| v0.5 | Docker + Tailscale + 多设备 | ?? 计划中 |

## 快速启动

```bash
cd C:\Users\Administrator\Desktop\项目\private-agent
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

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

### 5. 知识库管理
- ChromaDB 向量存储
- 支持本地文档导入
- 语义搜索

### 6. 长期记忆
- SQLite 存储
- 分类管理
- 增删改查

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/chat` | 聊天（JSON 响应） |
| POST | `/chat/stream` | 流式聊天（SSE） |
| POST | `/memory/remember` | 保存记忆 |
| GET | `/memory/list` | 查看记忆 |
| DELETE | `/memory/delete/{key}` | 删除记忆 |
| DELETE | `/memory/delete-all` | 删除所有记忆 |
| POST | `/knowledge/search` | 搜索知识库 |
| POST | `/ingest/local` | 导入本地笔记 |
| POST | `/ingest/web` | 导入网页文档 |
| POST | `/updates/check` | 检查文档更新 |
| GET | `/updates/recent` | 查看最近更新 |
| POST | `/review/weekly` | 生成本周复盘 |

## 测试

### 运行所有测试
```bash
pytest tests/ -v
```

### 测试类型
- **单元测试**: 99 个（工具函数、存储层、API 端点）
- **集成测试**: 6 个（端到端系统测试）
- **端到端测试**: 7 个（完整用户流程）
- **性能测试**: 3 个（响应时间和并发）
- **安全测试**: 5 个（输入验证和错误处理）

**总计：120 个测试，全部通过！**

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

## 架构图

详见 [ARCHITECTURE-v0.2.md](ARCHITECTURE-v0.2.md)

## 技术债务

详见 [TECH_DEBT.md](TECH_DEBT.md)

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

## 部署

### 本地开发
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 生产环境
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -m 'Add feature xxx'`)
4. 推送到分支 (`git push origin feature/xxx`)
5. 创建 Pull Request

## 许可证

MIT License

## 联系方式

- GitHub: https://github.com/zzj024/private-agent
- 作者: zzj024

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
