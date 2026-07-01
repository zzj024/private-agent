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
    conversation_id: int | str | None = None

class RememberRequest(BaseModel):
    key: str
    value: str
    category: str = "preference"

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

class CreateConversationRequest(BaseModel):
    title: str = "新对话"

class SaveMessageRequest(BaseModel):
    role: str    # "user" | "assistant"
    content: str

class RenameConversationRequest(BaseModel):
    title: str

class IngestLocalRequest(BaseModel):
    directory: str = "knowledge"

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


# ═══════════════════════════════════════════════
# 会话管理
# ═══════════════════════════════════════════════

@app.get("/conversations")
def list_conversations():
    """获取最近会话列表"""
    store = get_store()
    conversations = store.get_recent_conversations(limit=50)
    return {"conversations": conversations}


@app.post("/conversations")
def create_conversation(req: CreateConversationRequest):
    """创建新会话"""
    store = get_store()
    conv_id = store.create_conversation(title=req.title)
    conv = store.get_conversation(conv_id)
    return {"conversation": conv}


@app.get("/conversations/{conv_id}")
def get_conversation(conv_id: int):
    """获取会话详情及消息"""
    store = get_store()
    conv = store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = store.get_conversation_messages(conv_id)
    return {"conversation": conv, "messages": messages}


@app.post("/conversations/{conv_id}/messages")
def save_message(conv_id: int, req: SaveMessageRequest):
    """向会话追加一条消息"""
    store = get_store()
    conv = store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    store.save_message(conv_id, req.role, req.content)
    return {"status": "ok"}


@app.put("/conversations/{conv_id}/rename")
def rename_conversation(conv_id: int, req: RenameConversationRequest):
    """重命名会话"""
    store = get_store()
    success = store.rename_conversation(conv_id, req.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@app.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int):
    """删除会话及其所有消息"""
    store = get_store()
    success = store.delete_conversation(conv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@app.post("/ingest/local")
def ingest_local(req: IngestLocalRequest):
    """导入本地笔记到知识库"""
    from rag.chroma_store import get_chroma_store
    from rag.ingest_local import ingest_local_directory
    store = get_chroma_store()
    result = ingest_local_directory(req.directory, store)
    return result


