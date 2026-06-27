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
├── agent/        # LangGraph 工作流
├── llm/          # LLM 路由（Ollama 本地 / API）
├── memory/       # SQLite 存储
├── rag/          # Chroma 向量库 + 文档导入
├── tools/        # 工具函数
├── config/       # 配置
├── knowledge/    # 本地笔记来源
├── data/         # 数据存储
└── tests/        # 测试
```

## 相关文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构与实施规划
