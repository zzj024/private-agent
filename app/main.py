# 职责：FastAPI 应用入口，注册所有路由

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from memory.sqlite_store import get_store
from app.web import get_html
from config.settings import settings
from app.chat_service import ChatService
import json

chat_service = ChatService()


# 请求/响应模型
# ═══════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None  # 改为 str 类型

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

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return get_html()


@app.get("/health")
def health():
    """详细健康检查"""
    result = {"status": "ok", "version": "0.1.0"}
    try:
        import httpx
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            result["ollama"] = {"status": "ok", "models": models}
        else:
            result["ollama"] = {"status": "error"}
            result["status"] = "degraded"
    except Exception as e:
        result["ollama"] = {"status": "down"}
        result["status"] = "degraded"
    return result


@app.post("/chat")
async def chat(req: ChatRequest):
    """聊天——使用 ChatService 统一管线"""
    try:
        final_response = None
        async for event_str in chat_service.stream_events(req.message, conversation_id=req.conversation_id):
            event = json.loads(event_str)
            # 只关心 final 事件（LLM 的最终回复）
            if event["event"] == "final":
                final_response = event["data"]["content"]
        return {"response": final_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式聊天——ChatService 事件转 SSE"""
    async def event_generator():
        async for event_str in chat_service.stream_events(req.message, conversation_id=req.conversation_id):
            # 逐条推送所有事件（meta、stage、final、done）
            yield f"data: {event_str}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


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


@app.delete("/memory/delete/{key}")
def delete_memory(key: str):
    """删除一条记忆"""
    store = get_store()
    success = store.delete_memory(key)
    if success:
        return {"status": "ok", "message": f"已删除：{key}"}
    return {"status": "not_found", "message": f"未找到：{key}"}


@app.delete("/memory/delete-all")
def delete_all_memories():
    """删除全部记忆"""
    store = get_store()
    memories = store.list_memories()
    count = len(memories)
    for m in memories:
        store.delete_memory(m["key"])
    return {"status": "ok", "message": f"已删除全部 {count} 条记忆"}


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