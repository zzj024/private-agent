# 职责：FastAPI 应用入口，注册所有路由

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from memory.sqlite_store import get_store
from agent.graph import run_agent
from app.web import get_html

# ═══════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None

class RememberRequest(BaseModel):
    key: str
    value: str
    category: str = "preference"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

class IngestLocalRequest(BaseModel):
    directory: str = "knowledge"

class IngestWebRequest(BaseModel):
    url: str
    topic: str = ""

# ═══════════════════════════════════════════════
# 创建应用
# ═══════════════════════════════════════════════

app = FastAPI(title="Private Agent", version="0.1.0")

# 挂载静态文件目录
import os
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ═══════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def index():
    """极简前端页面"""
    return get_html()


@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/chat")
def chat(req: ChatRequest):
    """聊天入口，走 LangGraph 工作流"""
    try:
        response = run_agent(req.message, req.conversation_id)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/remember")
def remember(req: RememberRequest):
    """保存长期记忆"""
    store = get_store()
    store.save_memory(req.key, req.value, req.category)
    return {"status": "ok", "message": f"已记住：{req.key} = {req.value}"}


@app.get("/memory/list")
def list_memories(category: str | None = None):
    """查看长期记忆"""
    store = get_store()
    memories = store.list_memories(category)
    return {"memories": memories}


@app.post("/knowledge/search")
def search_knowledge(req: SearchRequest):
    """搜索知识库"""
    from tools.knowledge_tools import search_knowledge as kb_search
    context = kb_search(req.query)
    return {
        "query": req.query,
        "context": context,
        "has_results": bool(context),
    }


@app.post("/ingest/local")
def ingest_local(req: IngestLocalRequest):
    """导入本地笔记到知识库"""
    from rag.chroma_store import get_chroma_store
    from rag.ingest_local import ingest_local_directory
    store = get_chroma_store()
    result = ingest_local_directory(req.directory, store)
    return result


@app.post("/ingest/web")
def ingest_web(req: IngestWebRequest):
    """导入网页文档（占位，Phase 2 实现）"""
    return {
        "status": "ok",
        "message": f"已记录导入请求：{req.url}（完整实现在 Phase 2）",
    }


@app.post("/updates/check")
def check_updates():
    """检查文档更新（占位，Phase 2 实现）"""
    return {"status": "ok", "message": "文档更新检查将在 Phase 2 实现"}


@app.get("/updates/recent")
def recent_updates(days: int = 7):
    """查看最近文档更新（占位，Phase 2 实现）"""
    return {"updates": [], "message": "文档更新将在 Phase 2 实现"}


@app.post("/review/weekly")
def weekly_review():
    """生成本周复盘（占位，Phase 2 实现）"""
    return {
        "review": "周复盘功能将在 Phase 2 实现",
    }
