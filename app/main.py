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

class AcceptCandidateRequest(BaseModel):
    key: str | None = None
    value: str | None = None
    category: str | None = None

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


# ═══════════════════════════════════════════════
# LLM 设置
# ═══════════════════════════════════════════════

@app.get("/settings/llm")
def get_llm_settings():
    """获取当前 LLM 配置"""
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_key": "***" if settings.llm_api_key else "",  # 不暴露完整 key
        "has_key": bool(settings.llm_api_key),
    }


class LLMSettingsRequest(BaseModel):
    provider: str = "ollama"
    model: str = ""
    base_url: str = ""
    api_key: str = ""


@app.post("/settings/llm/test")
def test_llm_connection(req: LLMSettingsRequest):
    """测试 LLM 连接"""
    import httpx
    provider = req.provider or settings.llm_provider
    model = req.model or settings.llm_model
    base_url = (req.base_url or settings.llm_base_url).rstrip("/")
    api_key = req.api_key or settings.llm_api_key

    try:
        if provider == "ollama":
            r = httpx.post(f"{base_url}/api/chat",
                          json={"model": model, "messages": [{"role":"user","content":"hi"}], "stream": False},
                          timeout=10)
            r.raise_for_status()
            return {"ok": True, "response": r.json()["message"]["content"][:200]}
        else:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            r = httpx.post(f"{base_url}/chat/completions",
                          json={"model": model, "messages": [{"role":"user","content":"hi"}], "max_tokens": 20},
                          headers=headers, timeout=10)
            r.raise_for_status()
            return {"ok": True, "response": r.json()["choices"][0]["message"]["content"][:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.put("/settings/llm")
def update_llm_settings(req: LLMSettingsRequest):
    """更新 LLM 配置，立即生效"""
    import os
    env_path = settings.project_root / ".env"

    existing = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    if req.provider:
        existing["LLM_PROVIDER"] = req.provider
    if req.model:
        existing["LLM_MODEL"] = req.model
    if req.base_url:
        existing["LLM_BASE_URL"] = req.base_url
    if req.api_key:
        existing["LLM_API_KEY"] = req.api_key

    env_path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n", encoding="utf-8")

    # 立即生效：更新内存中的 settings 对象
    settings.llm_provider = req.provider or settings.llm_provider
    settings.llm_model = req.model or settings.llm_model
    settings.llm_base_url = req.base_url or settings.llm_base_url
    settings.llm_api_key = req.api_key or settings.llm_api_key

    return {"status": "ok", "message": "配置已保存，立即生效"}


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
    """保存长期记忆。如果 key 已存在且值不同 → 创建冲突候选"""
    store = get_store()
    existing = store.get_memory(req.key)
    if existing and existing.get("value", "").strip() != req.value.strip():
        # 冲突 → 不覆盖，创建候选
        store.insert_memory_candidate(
            key=req.key, value=req.value, category=req.category,
            confidence=0.9, importance=0.8, sensitivity="low",
            action="store",
            evidence=f"手动保存，旧值: {existing['value']}",
            reason=f"[冲突] 旧值: {existing['value']} → 新值: {req.value}",
            source_conversation_id=None, source_message_ids="[]",
            status="pending",
        )
        return {"status": "conflict", "message": f"冲突: '{req.key}' 已存在，新值已提交审核"}
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
    """搜索知识库（返回格式化文本）"""
    from tools.knowledge_tools import search_knowledge as kb_search
    context = kb_search(req.query)
    return {
        "query": req.query,
        "context": context,
        "has_results": bool(context),
    }


@app.post("/knowledge/search/chunks")
def search_knowledge_chunks(req: SearchRequest):
    """搜索知识库（返回结构化 chunk 列表，支持分页）"""
    from tools.knowledge_tools import search_knowledge_chunks
    return search_knowledge_chunks(req.query, req.top_k)


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

    # 被动记忆提取：assistant 消息落库后触发后台提取
    if req.role == "assistant":
        from memory.passive_extractor import schedule_passive_memory_extraction
        schedule_passive_memory_extraction(conv_id)

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


# ═══════════════════════════════════════════════
# 知识库管理 — 异步上传 / 进度查询 / 分页浏览 / 删改
# ═══════════════════════════════════════════════

from pathlib import Path as _Path
from urllib.parse import unquote as _unquote
from fastapi import UploadFile, File as _File
from fastapi.responses import JSONResponse as _JSONResponse
import threading as _threading
import uuid as _uuid

_KB_COLLECTION = "personal_knowledge"
_KB_UPLOAD_DIR = _Path("knowledge/uploads")
_ALLOWED_SUFFIXES = {".md", ".txt"}
_PROGRESS_STORE = {}  # task_id → {"filename":..., "total":..., "done":..., "status":...}


def _safe_filename(filename: str) -> str:
    return _Path(filename or "").name.strip()


def _kb_error(message: str, status_code: int = 400):
    return _JSONResponse(status_code=status_code, content={"status": "error", "message": message})


@app.post("/knowledge/upload")
async def upload_knowledge_file(file: UploadFile = _File(...)):
    """切块 → 返回 task_id → 后台异步逐批 embedding + 写入"""
    fname = _safe_filename(file.filename)
    if not fname:
        return _kb_error("文件名为空", 400)
    suffix = _Path(fname).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        return _kb_error("仅支持 .md 和 .txt 文件", 400)

    _KB_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = _KB_UPLOAD_DIR / fname
    content = await file.read()
    if not content:
        return _kb_error("文件内容为空", 400)
    save_path.write_bytes(content)

    from rag.chunker import Chunker
    chunker = Chunker(chunk_size=300, overlap=50)
    chunks = chunker.chunk_file(save_path)
    if not chunks:
        return _kb_error("文件无法切块", 400)

    task_id = str(_uuid.uuid4())
    _PROGRESS_STORE[task_id] = {
        "filename": fname, "total": len(chunks), "done": 0,
        "status": "processing", "message": ""
    }

    def _background_import():
        try:
            from rag.chroma_store import get_chroma_store
            store = get_chroma_store()
            store.delete_file_chunks(fname, _KB_COLLECTION)

            # 每 10 块一批做 embedding + 写入
            batch_size = 10
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                texts = [c.text for c in batch]
                metadatas = [c.metadata for c in batch]
                ids = [f"{fname}_{i+j}" for j in range(len(batch))]
                store.add_documents(texts=texts, metadatas=metadatas, ids=ids, collection_name=_KB_COLLECTION)
                _PROGRESS_STORE[task_id]["done"] = min(i + batch_size, len(chunks))

            _PROGRESS_STORE[task_id]["status"] = "done"
            _PROGRESS_STORE[task_id]["message"] = f"成功导入 {len(chunks)} 个文本块"
        except Exception as e:
            _PROGRESS_STORE[task_id]["status"] = "error"
            _PROGRESS_STORE[task_id]["message"] = str(e)

    t = _threading.Thread(target=_background_import, daemon=True)
    t.start()

    return {"status": "ok", "task_id": task_id, "filename": fname, "total_chunks": len(chunks)}


@app.get("/knowledge/progress/{task_id}")
def get_knowledge_progress(task_id: str):
    """查询导入进度"""
    info = _PROGRESS_STORE.get(task_id)
    if not info:
        return _kb_error("任务不存在", 404)
    return info


@app.get("/knowledge/stats")
def get_knowledge_stats():
    """返回知识库按文件统计"""
    try:
        from rag.chroma_store import get_chroma_store
        return get_chroma_store().get_file_stats(_KB_COLLECTION)
    except Exception as e:
        return _JSONResponse(status_code=500, content={"status": "error", "message": f"获取统计失败: {str(e)}", "total_chunks": 0, "total_files": 0, "files": []})


@app.get("/knowledge/chunks/{filename}")
def get_file_chunks(filename: str, page: int = 1, page_size: int = 20):
    """分页获取某文件的文本块"""
    fname = _safe_filename(_unquote(filename))
    if not fname:
        return _kb_error("文件名为空", 400)
    try:
        from rag.chroma_store import get_chroma_store
        return get_chroma_store().get_file_chunks(fname, page=page, page_size=page_size, collection_name=_KB_COLLECTION)
    except Exception as e:
        return _kb_error(f"获取失败: {str(e)}", 500)


@app.delete("/knowledge/chunk/{chunk_id}")
def delete_knowledge_chunk(chunk_id: str):
    """删除单个文本块"""
    try:
        from rag.chroma_store import get_chroma_store
        ok = get_chroma_store().delete_chunk(chunk_id, _KB_COLLECTION)
        return {"status": "ok" if ok else "not_found", "chunk_id": chunk_id}
    except Exception as e:
        return _kb_error(f"删除失败: {str(e)}", 500)


@app.put("/knowledge/chunk/{chunk_id}")
def update_knowledge_chunk(chunk_id: str, body: dict):
    """修改单个文本块的内容（v0.5: 使用 Chroma 原生 update 方法）"""
    new_text = body.get("text", "")
    if not new_text.strip():
        return _kb_error("内容不能为空", 400)
    try:
        from rag.chroma_store import get_chroma_store
        result = get_chroma_store().update_chunk(chunk_id, new_text, _KB_COLLECTION)
        if result["ok"]:
            return {"status": "ok", "chunk_id": chunk_id}
        if result["reason"] == "not_found":
            return _JSONResponse(status_code=404, content={"status": "not_found", "chunk_id": chunk_id})
        return _kb_error(f"修改失败: {result.get('error', result['reason'])}", 500)
    except Exception as e:
        return _kb_error(f"修改失败: {str(e)}", 500)


@app.delete("/knowledge/chunks/{filename}")
def delete_knowledge_file_chunks(filename: str):
    """删除某个文件的全部 chunks"""
    fname = _safe_filename(_unquote(filename))
    if not fname:
        return _kb_error("文件名为空", 400)
    try:
        from rag.chroma_store import get_chroma_store
        deleted = get_chroma_store().delete_file_chunks(fname, _KB_COLLECTION)
        return {"status": "ok", "filename": fname, "deleted_chunks": deleted, "message": f"已删除 {fname} 的 {deleted} 个文本块"}
    except Exception as e:
        return _kb_error(f"删除失败: {str(e)}", 500)


@app.delete("/knowledge/collection")
def delete_knowledge_collection():
    """清空整个知识库（不可逆）"""
    try:
        from rag.chroma_store import get_chroma_store
        get_chroma_store().delete_collection(_KB_COLLECTION)
        return {"status": "ok", "message": "知识库已清空"}
    except Exception as e:
        return _kb_error(f"清空失败: {str(e)}", 500)


@app.get("/debug/chat-test")
def debug_chat_test(conv_id: int, message: str = "test"):
    """Debug: test history loading"""
    from agent.graph import _load_conversation_messages
    msgs = _load_conversation_messages(conv_id)
    return {
        "conv_id": conv_id,
        "history_count": len(msgs),
        "history": [{"role": type(m).__name__, "content": m.content[:100]} for m in msgs],
    }


@app.get("/messages/batch")
def get_messages_batch(ids: str = ""):
    """Batch get messages by comma-separated IDs (for evidence display)"""
    store = get_store()
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id list")
    messages = store.get_messages_by_ids(id_list)
    return {"messages": messages}


# ═══════════════════════════════════════════════
# 被动记忆提取 — 候选审核
# ═══════════════════════════════════════════════

@app.get("/memory/candidates")
def list_memory_candidates(status: str = "pending"):
    """列出候选记忆"""
    store = get_store()
    candidates = store.list_memory_candidates(status)
    return {"candidates": candidates}


@app.post("/memory/candidates/{candidate_id}/accept")
def accept_memory_candidate(candidate_id: int, req: AcceptCandidateRequest = AcceptCandidateRequest()):
    """接受一条候选 → 写入正式记忆（支持修改 key/value/category）"""
    store = get_store()
    candidate = store.get_memory_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Candidate already {candidate['status']}"
        )

    final_key = req.key or candidate["key"]
    final_value = req.value or candidate["value"]
    final_category = req.category or candidate["category"]

    # 检测是否覆盖了旧值
    existing = store.get_memory(final_key)
    overwritten = None
    if existing and existing.get("value", "").strip() != final_value.strip():
        overwritten = existing["value"]

    store.save_memory(
        key=final_key,
        value=final_value,
        category=final_category,
        confidence=candidate["confidence"],
        source="passive",
        evidence=candidate["evidence"],
        source_conversation_id=candidate["source_conversation_id"],
        source_message_ids=candidate["source_message_ids"],
        seen_count=1,
    )
    store.update_memory_candidate_status(candidate_id, "accepted")

    msg = f"已记住：{final_key}"
    if overwritten:
        msg = f"已更新：{final_key}（旧值: {overwritten} → 新值: {final_value}）"
    return {"status": "ok", "message": msg}


@app.post("/memory/candidates/{candidate_id}/reject")
def reject_memory_candidate(candidate_id: int):
    """拒绝一条候选"""
    store = get_store()
    candidate = store.get_memory_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Candidate already {candidate['status']}"
        )

    store.update_memory_candidate_status(candidate_id, "rejected")
    return {"status": "ok", "message": f"已拒绝：{candidate['key']}"}
